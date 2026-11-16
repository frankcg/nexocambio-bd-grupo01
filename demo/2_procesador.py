"""
NexoCambio · Demo, paso 2: procesador de features y scoring (dejarlo corriendo en una terminal).

Es un consumer group de Kafka. Por cada evento operacion_creada:
  1. actualiza las ventanas del cliente en Redis con un script Lua atómico (idempotente por offset);
  2. lee las features actualizadas en un solo viaje a Redis;
  3. aplica el modelo (Isolation Forest, el mismo del notebook de Databricks);
  4. guarda el riesgo de la operación y la pone en la cola del back-office (cola:riesgo).

En la arquitectura, el scoring es un servicio aparte que la API llama de forma síncrona; en la
demo, el mismo proceso hace ambas cosas para usar una sola terminal.

    .venv\\Scripts\\python demo/2_procesador.py
"""
import json
import pickle
import time
from datetime import datetime

from confluent_kafka import Consumer

from comun import (FEATURES_MODELO, LIMA, MODELO, TOPIC_OPERACIONES, clave, conectar_redis, kafka_conf,
                   leer_features, vector)

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


def puntuar(m, feats):
    score = float(-m["modelo"].score_samples([vector(feats)])[0])
    nivel = "ALTO" if score >= m["umbral_alto"] else "MEDIO" if score >= m["umbral_medio"] else "NORMAL"
    motivos = [f"{f}={feats[f]:g}" for f in FEATURES_MODELO if feats[f] is not None and feats[f] > m["p99"][f]]
    if feats["operaciones_24h"] >= 10:
        motivos.append(f"operaciones_24h={feats['operaciones_24h']}")
    return score, nivel, motivos


def procesar(r, actualizar, m, msg):
    recibido_ms = time.time() * 1000
    evento = json.loads(msg.value())
    op = evento["operacion"]
    id_cliente, codigo, monto = op["id_cliente"], op["codigo_operacion"], float(op["monto_usd"])
    ocurrido = datetime.fromisoformat(evento["ocurrido_en"])
    cuenta = op["cuenta_destino"]

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
    print(f"  Kafka (Confluent Cloud → procesador): {recibido_ms - msg.timestamp()[1]:6.0f} ms")
    print(f"  Redis · actualizar ventanas (Lua):    {t_lua:6.1f} ms")
    print(f"  Redis · leer features:                {t_leer:6.1f} ms")
    print(f"  Modelo · inferencia:                  {t_modelo:6.1f} ms")
    for f in ("operaciones_24h", "operaciones_30d", "monto_promedio_usd_90d", "ratio_cerca_umbral_90d"):
        print(f"    {f:<26}{antes[f]!s:>10} → {despues[f]!s:<10}")
    print(f"  Score {score_antes:.3f} → {score:.3f} · riesgo {nivel} · puesto {posicion} de "
          f"{r.zcard('cola:riesgo')} en la cola del back-office")
    if motivos:
        print(f"  Motivos: {', '.join(motivos)}")


def main():
    r = conectar_redis()
    actualizar = r.register_script(LUA_ACTUALIZAR)
    m = pickle.loads(MODELO.read_bytes())
    consumidor = Consumer(kafka_conf(**{"group.id": "procesador-features", "auto.offset.reset": "latest",
                                        "enable.auto.commit": False, "fetch.wait.max.ms": 100}))
    consumidor.subscribe([TOPIC_OPERACIONES], on_assign=lambda c, particiones: print(
        f"Escuchando {TOPIC_OPERACIONES} ({len(particiones)} particiones). Esperando eventos… (Ctrl+C para salir)"))
    try:
        while True:
            msg = consumidor.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print("Error de Kafka:", msg.error())
                continue
            procesar(r, actualizar, m, msg)
            consumidor.commit(msg, asynchronous=False)
    except KeyboardInterrupt:
        pass
    finally:
        consumidor.close()


if __name__ == "__main__":
    main()
