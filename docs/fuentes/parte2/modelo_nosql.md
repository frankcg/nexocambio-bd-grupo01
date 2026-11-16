# NexoCambio · Modelo de datos NoSQL (Redis como feature store en línea)

Grupo 1 · Curso de Base de Datos · Parte 2 · Amazon ElastiCache (Redis OSS / Valkey), modo clúster · complementa al modelo relacional de PostgreSQL

## 1. Principios de diseño

En PostgreSQL se modela **la realidad del negocio** (entidades normalizadas) y después se escriben las consultas. En Redis es al revés: **se modela a partir de las consultas**. El servicio de scoring hace siempre la misma pregunta: *"dame el estado reciente del cliente X, ya"*. Las decisiones que salen de esa pregunta son:

1. **Todo se accede por clave del cliente.** No hay joins: cada estructura responde una feature con uno o dos comandos de costo O(1) u O(log n).
2. **Colocalidad con *hash tags*.** Todas las claves de un cliente llevan `{id_cliente}` entre llaves (por ejemplo `cli:{41768}:perfil`). En modo clúster, Redis las ubica en el mismo *slot*, lo que permite leerlas en un *pipeline* y actualizarlas juntas con un script Lua atómico.
3. **Ventanas deslizantes nativas.** Se usan *sorted sets* (score = instante) para "últimas 24 horas" y *buckets diarios* en un hash para "últimos 30 y 90 días".
4. **Datos derivados y con caducidad.** Nada aquí es fuente de verdad. Cada clave tiene TTL o una poda explícita; si Redis se pierde, se reconstruye desde PostgreSQL y desde Kafka.
5. **Escrituras incrementales.** Cada evento suma (`HINCRBY`, `ZADD`) en lugar de recalcular el historial: el costo por evento es constante aunque el cliente tenga miles de operaciones.

## 2. Mapa de claves (*keyspace*)

| Clave | Tipo | Contenido | Escribe | Lee | Caducidad |
|---|---|---|---|---|---|
| `cli:{id}:perfil` | Hash | Atributos estables y features batch del cliente | Job nocturno (desde `v_features_cliente`) y procesador de eventos | Scoring | Sin TTL; se reescribe cada noche |
| `cli:{id}:diario` | Hash | Contadores por día: `n:AAAAMMDD`, `usd:…`, `umbral:…`, `noct:…`, `terc:…` | Procesador de eventos (`HINCRBY`) | Scoring (`HMGET` de 30 o 120 campos) | Poda diaria de campos de más de 120 días |
| `cli:{id}:ops24h` | Sorted set | score = epoch ms, miembro = `codigo\|monto_usd` | Procesador | Scoring (`ZCOUNT`, `ZRANGE`) | `ZREMRANGEBYSCORE` de más de 7 días |
| `cli:{id}:destinos` | Sorted set | score = último uso, miembro = id de cuenta destino | Procesador | Scoring (`ZCOUNT` últimos 30 días) | Poda de más de 90 días |
| `cta:{hash_cuenta}:clientes` | Set | Clientes distintos que enviaron a esa cuenta bancaria | Procesador | Scoring (`SCARD`) | TTL 180 días |
| `op:{codigo}:riesgo` | Hash | Score, nivel, motivos, versión del modelo | Scoring | Back-office | TTL 30 días |
| `cola:riesgo` | Sorted set | score = riesgo, miembro = código de operación pendiente | Scoring (`ZADD`); se quita al decidir (`ZREM`) | Back-office (`ZREVRANGE`) | Se vacía con las decisiones |
| `modelo:activo` | String | Versión del modelo en producción | Pipeline de ML | Scoring | — |
| `cot:{codigo}` | Hash | Cotización emitida: cliente, monto, vencimiento y estado (pendiente, convertida, vencida) | Procesador (al recibir la cotización) | Procesador (al vencer) | TTL 24 h |
| `cotizaciones:pendientes` | Sorted set | score = vencimiento en ms, miembro = código de cotización | Procesador (`ZADD`); se quita al convertirse o vencer (`ZREM`) | Procesador (`ZRANGEBYSCORE` hasta ahora) | Se vacía sola: cada cotización sale en minutos |
| `ofertas:recuperacion` | Stream | Acción comercial disparada por cada cotización vencida, con el riesgo del cliente | Procesador (`XADD`) | Área comercial y notificaciones (`XREAD`) | `MAXLEN` ≈ 10 000 |

## 3. Estructuras con ejemplos

### 3.1 Perfil del cliente · Hash `cli:{41768}:perfil`

Lo genera el job nocturno a partir de la vista `v_features_cliente` de la Parte 1. El procesador de eventos actualiza los campos que cambian durante el día.

```
HSET cli:{41768}:perfil
     codigo_cliente         CLI-06EZN7
     tipo_cliente           persona
     es_pep                 0
     antiguedad_dias        412
     monto_promedio_usd_90d 1489.20
     ratio_rechazo          0.042
     ratio_cuentas_terceros 0.000
     ratio_nocturno         0.010
     ultima_operacion       1792623600000      # epoch ms (lo actualiza el procesador)
     decididas              48                 # HINCRBY en cada decisión del back-office
     rechazadas             2
     actualizado_en         2026-10-22T03:00:00-05:00
```

### 3.2 Contadores diarios · Hash `cli:{41768}:diario`

Un campo por métrica y por día. Las ventanas de 30 y 90 días se obtienen leyendo solo los campos de esos días: `HMGET` de 30 campos es O(30), sin importar cuántas operaciones tenga el cliente.

```
HINCRBY      cli:{41768}:diario n:20261021      1          # operaciones del día
HINCRBYFLOAT cli:{41768}:diario usd:20261021    9850.00    # volumen USD del día
HINCRBY      cli:{41768}:diario umbral:20261021 1          # operaciones entre US$ 9 000 y 9 999,99
HINCRBY      cli:{41768}:diario noct:20261021   0          # operaciones entre 00:00 y 04:59
HINCRBY      cli:{41768}:diario terc:20261021   0          # destinos a cuentas de terceros
```

Vista lógica del hash:

```json
{
  "n:20261019": 3,  "usd:20261019": 27940.10, "umbral:20261019": 3,
  "n:20261020": 4,  "usd:20261020": 38211.55, "umbral:20261020": 4,
  "n:20261021": 2,  "usd:20261021": 19480.00, "umbral:20261021": 2, "noct:20261021": 0
}
```

### 3.3 Velocidad de las últimas 24 horas · Sorted set `cli:{41768}:ops24h`

```
ZADD  cli:{41768}:ops24h 1792608120000 "NX-7KQ2M9TA|9850.00"
ZADD  cli:{41768}:ops24h 1792611940000 "NX-PB3L8QWE|9620.00"
ZREMRANGEBYSCORE cli:{41768}:ops24h -inf (1792003320000        # poda: más de 7 días
ZCOUNT cli:{41768}:ops24h 1792536720000 +inf                    # → operaciones en las últimas 24 h
```

### 3.4 Cuentas destino · Sorted set `cli:{41768}:destinos` y Set `cta:{…}:clientes`

```
ZADD   cli:{41768}:destinos 1792611940000 "cta:193771"     # re-ZADD actualiza la fecha de último uso
ZCOUNT cli:{41768}:destinos 1790019940000 +inf             # → cuentas destino distintas en 30 días
SADD   cta:{9f2c41e0}:clientes 41768                         # hash SHA-256 truncado del número de cuenta
SCARD  cta:{9f2c41e0}:clientes                               # → > 1: cuenta compartida entre clientes
```

El set por cuenta detecta **redes de "mulas"**: una cuenta bancaria que reciben varios clientes sin relación. Es una relación de grafo que en SQL exige un auto-join sobre toda la tabla de operaciones; aquí cuesta un `SCARD`. Se guarda un hash del número de cuenta, no el número, para no duplicar datos sensibles fuera de PostgreSQL.

### 3.5 Resultado del scoring · Hash `op:{NX-7KQ2M9TA}:riesgo` y cola `cola:riesgo`

```
HSET op:{NX-7KQ2M9TA}:riesgo
     score 0.87  nivel ALTO  modelo v3.2  calculado_en 2026-10-21T10:15:40-05:00
     motivos "[\"cerca_umbral_30d=0.92\",\"operaciones_24h=9\",\"cuenta_compartida=1\"]"
EXPIRE op:{NX-7KQ2M9TA}:riesgo 2592000                       # 30 días
ZADD  cola:riesgo 0.87 NX-7KQ2M9TA                             # cola del back-office
ZREVRANGE cola:riesgo 0 49 WITHSCORES                          # → 50 operaciones más riesgosas primero
ZREM  cola:riesgo NX-7KQ2M9TA                                  # al decidir (En proceso / Rechazada)
```

## 4. De la feature SQL (Parte 1) al comando Redis

| Feature (Parte 1) | En PostgreSQL | En Redis (en línea) | Costo |
|---|---|---|---|
| `operaciones_30d` | `count(*)` sobre `operacion` filtrada por cliente y fecha | Suma de `HMGET cli:{id}:diario n:…` (30 campos) | O(30) |
| `operaciones_24h` *(nueva)* | `count(*)` con rango de horas | `ZCOUNT cli:{id}:ops24h now-24h +inf` | O(log n) |
| `monto_promedio_usd_90d` | `avg(monto_usd)` con join a cotización y tasa | `HGET perfil` (batch) o Σ`usd` / Σ`n` de 90 campos | O(1) / O(90) |
| `dias_desde_ultima_operacion` | `max(fecha_operacion)` | `HGET cli:{id}:perfil ultima_operacion` | O(1) |
| `ratio_rechazo` | conteo condicional sobre todo el historial | `HMGET perfil rechazadas decididas` | O(1) |
| `ratio_cerca_umbral_90d` | `avg(CASE …)` sobre 90 días | Σ`umbral` / Σ`n` de 90 campos | O(90) |
| `ratio_cuentas_terceros` | join operación–cuenta–subtipo | Σ`terc` / Σ`n` (y valor batch en el perfil) | O(30) |
| `cuentas_destino_30d` *(nueva)* | `count(DISTINCT id_cuenta_destino)` | `ZCOUNT cli:{id}:destinos now-30d +inf` | O(log n) |
| `cuenta_compartida` *(nueva)* | auto-join de operaciones por cuenta destino | `SCARD cta:{hash}:clientes` | O(1) |
| `variacion_monto_30d` | dos `avg` con FILTER | (Σ`usd` / Σ`n` de 30 días) / (de los días 31–120) | O(120) |
| `ratio_nocturno` | `avg(CASE hora < 5)` | Σ`noct` / Σ`n` | O(30) |

El servicio de scoring envía todos estos comandos en **un solo *pipeline*** (un viaje de red, unos 0,5 a 1 ms en la misma zona de disponibilidad). Además suma los datos de la operación actual, que todavía no llegó por el flujo de eventos.

## 5. Actualización atómica por evento (script Lua)

El procesador de features (un *consumer group* de Kafka) recibe los eventos de un cliente **en orden**, porque la clave del mensaje es `id_cliente` y todos sus eventos caen en la misma partición. Cada evento `operacion_creada` ejecuta un script, de modo que las cuatro estructuras del cliente se actualizan juntas o no se actualiza ninguna:

```lua
-- KEYS: diario, ops24h, destinos, perfil   (mismo hash tag {id_cliente} → mismo slot)
-- ARGV: dia, ts_ms, codigo, monto_usd, es_umbral, es_nocturna, es_tercero, id_cuenta
redis.call('HINCRBY',      KEYS[1], 'n:'..ARGV[1], 1)
redis.call('HINCRBYFLOAT', KEYS[1], 'usd:'..ARGV[1], ARGV[4])
redis.call('HINCRBY',      KEYS[1], 'umbral:'..ARGV[1], ARGV[5])
redis.call('HINCRBY',      KEYS[1], 'noct:'..ARGV[1], ARGV[6])
redis.call('HINCRBY',      KEYS[1], 'terc:'..ARGV[1], ARGV[7])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3]..'|'..ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', '(' .. (ARGV[2] - 7*86400000))
redis.call('ZADD', KEYS[3], ARGV[2], 'cta:'..ARGV[8])
redis.call('HSET', KEYS[4], 'ultima_operacion', ARGV[2])
return 1
```

La clave `cta:{hash}:clientes` no comparte el hash tag del cliente, así que se actualiza con un `SADD` aparte, que es idempotente. Si el evento se reprocesa (entrega *at-least-once* de Kafka, por ejemplo tras reiniciar el consumidor antes de confirmar el *offset*), los contadores podrían duplicarse. Para evitarlo, el procesador guarda el último *offset* aplicado por cliente (`HSET perfil ult_offset …`) y descarta los eventos ya vistos. Como los eventos de un cliente están siempre en la misma partición, su *offset* solo crece.

## 6. Evento de negocio en Kafka (JSON)

Lo produce el conector CDC (Debezium) a partir del WAL de PostgreSQL, ya enriquecido con el monto en USD. Es el contrato entre el núcleo relacional y el mundo de streaming, y su esquema se registra en el **Schema Registry** de Confluent para que productores y consumidores no se desalineen.

| Topic | Eventos | Clave | Particiones | Retención |
|---|---|---|---|---|
| `nexocambio.cotizaciones` | `cotizacion_emitida` (segundo uso: recuperación de cotizaciones) | `id_cliente` | 6 | 7 días |
| `nexocambio.operaciones` | `operacion_creada` (incluye la cotización de origen) | `id_cliente` | 6 | 7 días |
| `nexocambio.comprobantes` | `comprobante_cargado` | `id_cliente` | 6 | 7 días |
| `nexocambio.estados` | `estado_cambiado` (incluye el analista y el motivo de rechazo) | `id_cliente` | 6 | 7 días |
| `nexocambio.clientes` | `cliente_registrado` | `id_cliente` | 3 | compactado |

Seis particiones bastan con holgura: el pico actual es de 73 eventos por minuto y, con 10 veces más, de unos 12 por segundo. El topic de clientes es **compactado**: Kafka guarda el último evento de cada cliente, que sirve para reconstruir perfiles.

Mensaje en `nexocambio.operaciones` (clave `41768`):

```json
{
  "tipo_evento": "operacion_creada",
  "version": 1,
  "id_evento": "6c1e2f9a-8d4b-4a7e-9f0e-3b2d51c7a8e4",
  "ocurrido_en": "2026-10-21T10:15:32-05:00",
  "operacion": {
    "codigo_operacion": "NX-7KQ2M9TA",
    "id_cliente": 41768,
    "modalidad": "casa",
    "moneda_origen": "USD",
    "moneda_destino": "PEN",
    "monto_origen": 9850.00,
    "monto_usd": 9850.00,
    "tasa": 3.4126500000,
    "tasa_preferencial": true,
    "estado": "Pendiente de comprobante",
    "cuenta_destino": { "id_cuenta": 193771, "tipo": "banco", "banco": "BCP", "titular_es_cliente": true }
  }
}
```

La retención de 7 días permite reprocesar los eventos si cambia la lógica de una feature: basta con mover el *offset* del consumer group hacia atrás.

## 7. Vector de features para el modelo (documento JSON)

Es lo que el servicio de scoring arma con los resultados del *pipeline* y entrega al modelo. El mismo documento, con la etiqueta posterior del analista, se guarda en el Data Lake para reentrenar. Así se evita el *training-serving skew*: se entrena con las mismas features que se usan en producción.

```json
{
  "codigo_operacion": "NX-7KQ2M9TA",
  "id_cliente": 41768,
  "calculado_en": "2026-10-21T10:15:40-05:00",
  "contexto": { "tipo_cliente": "persona", "es_pep": false, "antiguedad_dias": 412 },
  "operacion_actual": { "monto_usd": 9850.00, "hora_local": 10, "modalidad": "casa", "tasa_preferencial": true },
  "features": {
    "operaciones_24h": 9,
    "operaciones_30d": 41,
    "monto_promedio_usd_90d": 9488.70,
    "dias_desde_ultima_operacion": 0,
    "ratio_rechazo": 0.042,
    "ratio_cerca_umbral_90d": 0.92,
    "ratio_cuentas_terceros": 0.00,
    "cuentas_destino_30d": 3,
    "cuenta_compartida": 1,
    "variacion_monto_30d": 1.04,
    "ratio_nocturno": 0.00
  },
  "resultado": { "score": 0.87, "nivel": "ALTO", "modelo": "v3.2" },
  "etiqueta": { "decision_backoffice": "Rechazada", "motivo": "Alerta de cumplimiento: operación inusual (UIF)" }
}
```

## 8. Dimensionamiento y operación

| Estructura | Elementos (hoy) | Tamaño aproximado |
|---|---|---|
| `cli:{id}:perfil` | 50 000 clientes × ≈ 15 campos | ≈ 20 MB |
| `cli:{id}:diario` | 23 700 activos × ≈ 50 campos (120 días) | ≈ 60 MB |
| `ops24h`, `destinos` | 7–90 días por cliente activo | ≈ 15 MB |
| `cta:{…}:clientes` | ≈ 160 000 cuentas bancarias | ≈ 25 MB |
| `op:{…}:riesgo` + `cola:riesgo` | ≈ 80 000 operaciones (30 días) | ≈ 30 MB |
| `cot:{…}` + `cotizaciones:pendientes` + `ofertas:recuperacion` | ≈ 5 700 cotizaciones al día (TTL 24 h) y 10 000 ofertas | ≈ 5 MB |
| **Total** | | **≈ 155 MB hoy · ≈ 1,5 GB con 10× de crecimiento** |

- **Nodo:** un clúster pequeño (por ejemplo `cache.r7g.large`, 13 GB) con una réplica en otra zona de disponibilidad. El volumen cabe holgadamente en memoria incluso con el crecimiento proyectado; la réplica es para disponibilidad, no para capacidad.
- **Persistencia:** snapshots diarios. No se necesita durabilidad estricta: el estado se reconstruye con el job batch desde PostgreSQL más los últimos 7 días de Kafka.
- **Seguridad:** cifrado en tránsito y en reposo; no se guardan nombres, documentos ni números de cuenta, solo IDs internos y hashes. Los datos personales permanecen en PostgreSQL.
- **Si Redis no responde:** el scoring calcula las features de ese cliente directamente en PostgreSQL, con las mismas consultas de la Parte 1. El índice `idx_operacion_cliente_fecha` (O1) lee el historial del cliente en menos de 1 ms, y con los joins a cotización y tasa el cálculo toma pocos milisegundos: aceptable para un modo degradado, aunque no para todo el tráfico. Si eso también falla, se usan reglas simples y la operación **no se bloquea**: la validación humana del back-office sigue funcionando igual.

## 9. Segundo uso: recuperación de cotizaciones abandonadas

La misma infraestructura (Kafka, el procesador y Redis) sirve a un objetivo comercial: cuando un cliente registrado cotiza y la tasa garantizada vence sin que opere, se le ofrece una acción para que termine la operación. La pregunta que se modela es *"¿qué cotizaciones vencieron hace un instante sin operación?"*.

1. Llega `cotizacion_emitida` → `HSET cot:{codigo}` (con `HSETNX` del estado para ignorar eventos repetidos) y `ZADD cotizaciones:pendientes vence_ms codigo`.
2. Llega `operacion_creada` con esa cotización → `ZREM cotizaciones:pendientes codigo`: ya no está abandonada.
3. Cada segundo, el procesador saca las vencidas con un script Lua atómico. Si hubiera varios procesadores, cada cotización la atiende uno solo:

```lua
-- KEYS: cotizaciones:pendientes · ARGV: ahora_ms, máximo por llamada
local vencidas = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
if #vencidas > 0 then redis.call('ZREM', KEYS[1], unpack(vencidas)) end
return vencidas
```

4. Por cada vencida, lee las features del cliente (sección 4) y calcula su **score de riesgo**. Si es ALTO, **no se ofrece ningún incentivo**; si no, se decide la acción según el monto, y se registra en el stream `ofertas:recuperacion`:

| Situación | Acción |
|---|---|
| Cliente de riesgo ALTO | Ninguna (solo se registra): cumplimiento manda sobre la venta |
| Monto desde US$ 5 000 | Mantener la tasa preferencial 5 minutos más |
| Monto entre US$ 4 000 y 4 999 | Ofrecer la tasa preferencial si sube a US$ 5 000 |
| Otros montos | Mantener la tasa 5 minutos más |

Se usa un *sorted set* por vencimiento y no las notificaciones de expiración de Redis (*keyspace notifications*) porque estas se pierden si el procesador está caído en ese instante. Con el *sorted set*, una cotización vencida espera en la lista hasta que alguien la atiende.
