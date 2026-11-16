"""
NexoCambio · Demo, paso 2: procesador de eventos (dejarlo corriendo en una terminal).

Es un consumer group de Kafka que atiende dos usos de la misma arquitectura:

Cumplimiento · por cada operacion_creada (topic nexocambio.operaciones):
  1. actualiza las ventanas del cliente en Redis con un script Lua atómico (idempotente por offset);
  2. lee las features actualizadas en un solo viaje a Redis;
  3. aplica el modelo (Isolation Forest, el mismo del notebook de Databricks);
  4. guarda el riesgo de la operación y la pone en la cola del back-office (cola:riesgo).

Ingresos · por cada cotizacion_emitida (topic nexocambio.cotizaciones):
  1. la registra en Redis como pendiente, con su vencimiento;
  2. si llega la operación de esa cotización, la marca como convertida;
  3. si vence sin operación, consulta el riesgo del cliente y decide una acción comercial:
     a un cliente de riesgo ALTO no se le ofrece ningún incentivo.

En la arquitectura, el scoring es un servicio aparte que la API llama de forma síncrona; en la
demo, el mismo proceso hace todo para usar una sola terminal.

    .venv\\Scripts\\python demo/2_procesador.py
"""
import json
import pickle
import time
from datetime import datetime

from confluent_kafka import Consumer

from comun import (FEATURES_MODELO, MODELO, TOPIC_COTIZACIONES, TOPIC_OPERACIONES,
                   UMBRAL_PREFERENCIAL_USD, clave, conectar_redis, kafka_conf, leer_features, vector)

# Actualización atómica de las ventanas del cliente (modelo_nosql.pdf, sección 5).
LUA_ACTUALIZAR = """
-- KEYS: diario, ops24h, destinos, perfil (mismo hash tag {id_cliente} → mismo slot)
-- ARGV: dia, ts_ms, codigo, monto_usd, es_umbral, es_nocturna, es_tercero, id_cuenta, offset
local ult = tonumber(redis.call('HGET', KEYS[4], 'ult_offset') or '-1')
if tonumber(ARGV[9]) <= ult then return 0 end          -- evento ya aplicado (at-least-once)
redis.call('HINCRBY',      KEYS[1], 'n:' .. ARGV[1], 1)
redis.call('HINCRBYFLOAT', KEYS[1], 'usd:' .. ARGV[1], ARGV[4])
redis.call('HINCRBY',      KEYS[1], 'umbral:' .. ARGV[1], ARGV[5])
redis.call('HINCRBY',      KEYS[1], 'noct:' .. ARGV[1], ARGV[6])
redis.call('HINCRBY',      KEYS[1], 'terc:' .. ARGV[1], ARGV[7])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3] .. '|' .. ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', '(' .. (tonumber(ARGV[2]) - 7 * 86400000))
redis.call('ZADD', KEYS[3], ARGV[2], 'cta:' .. ARGV[8])
redis.call('HSET', KEYS[4], 'ultima_operacion', ARGV[2], 'ult_offset', ARGV[9])
return 1
"""

# Saca de la lista de pendientes las cotizaciones ya vencidas, de forma atómica: si hubiera
# varios procesadores, cada cotización vencida la atiende uno solo.
LUA_VENCIDAS = """
-- KEYS: cotizaciones:pendientes · ARGV: ahora_ms, máximo por llamada
local vencidas = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
if #vencidas > 0 then redis.call('ZREM', KEYS[1], unpack(vencidas)) end
return vencidas
"""

PENDIENTES, OFERTAS, METRICAS = "cotizaciones:pendientes", "ofertas:recuperacion", "metricas:cotizaciones"


def puntuar(m, feats):
    score = float(-m["modelo"].score_samples([vector(feats)])[0])
    nivel = "ALTO" if score >= m["umbral_alto"] else "MEDIO" if score >= m["umbral_medio"] else "NORMAL"
    motivos = [f"{f}={feats[f]:g}" for f in FEATURES_MODELO if feats[f] is not None and feats[f] > m["p99"][f]]
    if feats["operaciones_24h"] >= 10:
        motivos.append(f"operaciones_24h={feats['operaciones_24h']}")
    return score, nivel, motivos


def latencia_kafka(msg):
    return time.time() * 1000 - msg.timestamp()[1]


# --- Cumplimiento: operaciones ---------------------------------------------------

def procesar_operacion(r, actualizar, m, msg, ev):
    op = ev["operacion"]
    id_cliente, codigo, monto = op["id_cliente"], op["codigo_operacion"], float(op["monto_usd"])
    ocurrido = datetime.fromisoformat(ev["ocurrido_en"])
    cuenta = op["cuenta_destino"]
    lat_kafka = latencia_kafka(msg)

    # Si viene de una cotización pendiente, esa cotización ya no se abandonó.
    if op.get("codigo_cotizacion"):
        a_tiempo = r.zrem(PENDIENTES, op["codigo_cotizacion"])
        r.hset(f"cot:{op['codigo_cotizacion']}", "estado", "convertida" if a_tiempo else "convertida_tarde")
        r.hincrby(METRICAS, "convertidas")
        print(f"\n✓ Cotización {op['codigo_cotizacion']} convertida en operación "
              f"{'antes de vencer: no se dispara ninguna acción.' if a_tiempo else 'después de vencer.'}")

    antes = leer_features(r, id_cliente)
    score_antes, _, _ = puntuar(m, antes)

    t0 = time.perf_counter()
    aplicado = actualizar(keys=[clave(id_cliente, c) for c in ("diario", "ops24h", "destinos", "perfil")],
                          args=[ocurrido.strftime("%Y%m%d"), int(ocurrido.timestamp() * 1000), codigo, monto,
                                int(9000 <= monto < 10000), int(ocurrido.hour < 5),
                                int(cuenta["tipo"] == "banco" and not cuenta["titular_es_cliente"]),
                                cuenta["id_cuenta"], msg.offset()])
    t_lua = (time.perf_counter() - t0) * 1000
    if not aplicado:
        print(f"\n· {codigo}: evento repetido (offset {msg.offset()}), se descarta.")
        return

    t0 = time.perf_counter()
    despues = leer_features(r, id_cliente)
    t_leer = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    score, nivel, motivos = puntuar(m, despues)
    t_modelo = (time.perf_counter() - t0) * 1000

    r.hset(f"op:{{{codigo}}}:riesgo", mapping={"score": round(score, 4), "nivel": nivel,
                                                "motivos": json.dumps(motivos), "modelo": "isolation_forest"})
    r.expire(f"op:{{{codigo}}}:riesgo", 30 * 86400)
    r.zadd("cola:riesgo", {codigo: score})
    posicion = r.zrevrank("cola:riesgo", codigo) + 1

    print(f"\n● {codigo} · cliente {id_cliente} · US$ {monto:,.2f} · partición {msg.partition()}, offset {msg.offset()}")
    print(f"  Kafka (Confluent Cloud → procesador): {lat_kafka:6.0f} ms")
    print(f"  Redis · actualizar ventanas (Lua):    {t_lua:6.1f} ms")
    print(f"  Redis · leer features:                {t_leer:6.1f} ms")
    print(f"  Modelo · inferencia:                  {t_modelo:6.1f} ms")
    for f in ("operaciones_24h", "operaciones_30d", "ratio_cerca_umbral_90d", "ratio_nocturno"):
        print(f"    {f:<26}{antes[f]!s:>10} → {despues[f]!s:<10}")
    print(f"  Score {score_antes:.3f} → {score:.3f} · riesgo {nivel} · puesto {posicion} de "
          f"{r.zcard('cola:riesgo')} en la cola del back-office")
    if motivos:
        print(f"  Motivos: {', '.join(motivos)}")


# --- Ingresos: cotizaciones --------------------------------------------------------

def procesar_cotizacion(r, msg, ev):
    cot = ev["cotizacion"]
    codigo = cot["codigo_cotizacion"]
    vence_ms = int(time.time() * 1000) + cot["vigencia_s"] * 1000  # reloj real: la tasa vence de verdad
    if not r.hsetnx(f"cot:{codigo}", "estado", "pendiente"):
        return  # evento repetido
    r.hset(f"cot:{codigo}", mapping={"id_cliente": cot["id_cliente"], "codigo_cliente": cot["codigo_cliente"],
                                     "monto_usd": cot["monto_usd"], "vence_ms": vence_ms})
    r.expire(f"cot:{codigo}", 86400)
    r.zadd(PENDIENTES, {codigo: vence_ms})
    r.hincrby(METRICAS, "emitidas")
    print(f"\n◇ {codigo} · {cot['codigo_cliente']} cotiza US$ {cot['monto_usd']:,.2f} · "
          f"tasa garantizada {cot['vigencia_s']} s · Kafka {latencia_kafka(msg):.0f} ms")


def accion_comercial(nivel, monto):
    """Regla de negocio de la recuperación. Devuelve None si no se ofrece nada."""
    if nivel == "ALTO":
        return None
    if monto >= UMBRAL_PREFERENCIAL_USD:
        return "mantener la tasa preferencial 5 minutos más"
    if monto >= 4000:
        return f"ofrecer la tasa preferencial si sube a US$ {UMBRAL_PREFERENCIAL_USD:,}"
    return "mantener la tasa 5 minutos más"


def atender_vencidas(r, vencidas, m):
    for codigo in vencidas(keys=[PENDIENTES], args=[int(time.time() * 1000), 50]):
        t0 = time.perf_counter()
        cot = r.hgetall(f"cot:{codigo}")
        id_cliente, monto = int(cot["id_cliente"]), float(cot["monto_usd"])
        score, nivel, _ = puntuar(m, leer_features(r, id_cliente))
        accion = accion_comercial(nivel, monto)
        r.hset(f"cot:{codigo}", "estado", "vencida")
        r.hincrby(METRICAS, "vencidas")
        r.hincrby(METRICAS, "ofertas" if accion else "sin_oferta")
        r.xadd(OFERTAS, {"codigo_cotizacion": codigo, "id_cliente": id_cliente, "monto_usd": monto,
                         "riesgo": nivel, "score": round(score, 4), "accion": accion or "ninguna"},
               maxlen=10_000, approximate=True)
        t_decision = (time.perf_counter() - t0) * 1000

        print(f"\n◆ {codigo} venció sin operación · {cot['codigo_cliente']} · US$ {monto:,.2f}")
        print(f"  Riesgo del cliente: {nivel} (score {score:.3f}) · decisión en {t_decision:.1f} ms")
        if accion:
            print(f"  → Acción comercial: {accion}. Se notifica al cliente.")
        else:
            print("  → Sin incentivo: el cliente es de riesgo ALTO. Cumplimiento manda sobre la venta.")
        metricas = r.hgetall(METRICAS)
        print(f"  Cotizaciones: {metricas.get('emitidas', 0)} emitidas · {metricas.get('convertidas', 0)} convertidas"
              f" · {metricas.get('vencidas', 0)} vencidas · {metricas.get('ofertas', 0)} ofertas enviadas")


def main():
    r = conectar_redis()
    actualizar = r.register_script(LUA_ACTUALIZAR)
    vencidas = r.register_script(LUA_VENCIDAS)
    m = pickle.loads(MODELO.read_bytes())
    consumidor = Consumer(kafka_conf(**{"group.id": "procesador-features", "auto.offset.reset": "latest",
                                        "enable.auto.commit": False, "fetch.wait.max.ms": 100}))
    topics = [TOPIC_OPERACIONES, TOPIC_COTIZACIONES]
    consumidor.subscribe(topics, on_assign=lambda c, particiones: print(
        f"Escuchando {' y '.join(topics)} ({len(particiones)} particiones). Esperando eventos… (Ctrl+C para salir)"))
    try:
        while True:
            msg = consumidor.poll(0.5)
            atender_vencidas(r, vencidas, m)
            if msg is None:
                continue
            if msg.error():
                print("Error de Kafka:", msg.error())
                continue
            ev = json.loads(msg.value())
            if msg.topic() == TOPIC_COTIZACIONES:
                procesar_cotizacion(r, msg, ev)
            else:
                procesar_operacion(r, actualizar, m, msg, ev)
            consumidor.commit(msg, asynchronous=False)
    except KeyboardInterrupt:
        pass
    finally:
        consumidor.close()


if __name__ == "__main__":
    main()
