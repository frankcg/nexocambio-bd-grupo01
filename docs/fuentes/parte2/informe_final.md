<div class="portada">
<div class="institucion">UTEC Posgrado · Maestría · Curso de Base de Datos</div>
<div class="titulo">NexoCambio</div>
<div class="subtitulo">Parte 2 · Arquitectura de datos para Ciencia de Datos e Inteligencia Artificial: detección de operaciones inusuales en tiempo real</div>
<div class="datos">
<p><strong>Grupo 1</strong></p>
<p>Integrantes: Frank Laura · Josue Campos · Mauricio Vallejos</p>
<p>Docente: Luis Chicoma</p>
<p>Lima, noviembre de 2026</p>
</div>
</div>

# Contenido

1. Definición del caso de IA
2. Caracterización del problema
3. Selección de tecnología
4. Modelo de datos NoSQL
5. Arquitectura propuesta
6. Comparación entre PostgreSQL y Redis
7. ¿Por qué usar ambas tecnologías? Polyglot Persistence
8. Hoja de ruta, riesgos y conclusiones

**Entregables de la Parte 2** (carpeta `grupo_01/`):

| Archivo | Contenido |
|---|---|
| `informe_final.pdf` | Este documento |
| `arquitectura.pdf` | Diagrama de arquitectura, flujos, secuencia de scoring y presupuesto de latencia |
| `modelo_nosql.pdf` | Diseño de claves en Redis, ejemplos, equivalencia con las features SQL, topics y eventos de Kafka y dimensionamiento |

Este documento amplía la Parte 1 (`informe.pdf`), que contiene el modelo relacional en PostgreSQL, las consultas de negocio y las features que aquí se ponen en producción.

# 1. Definición del caso de IA

**Caso:** detección de **operaciones inusuales** (posible lavado de activos o fraude) en tiempo real. Cada operación recibe un puntaje de riesgo **en el momento en que el cliente sube su comprobante**, antes de que un analista la revise. Con ese puntaje:

- la cola del back-office se ordena por riesgo y no por orden de llegada;
- las operaciones de riesgo alto pasan a un supervisor de cumplimiento;
- se alimenta el reporte de operaciones sospechosas (ROS) ante la UIF-Perú. Las casas de cambio son sujetos obligados a registrar sus operaciones y a reportar las sospechosas.

**Por qué este caso y no otro.** Sale directamente de los hallazgos de la Parte 1:

| Evidencia (Parte 1) | Qué muestra |
|---|---|
| C2 · rechazos por banco | El motivo de rechazo más frecuente en **todos** los bancos es la *alerta de cumplimiento*, no un error operativo. |
| C6 · top 3 clientes por mes | Los dos clientes de mayor volumen, todos los meses, tienen un patrón de **fraccionamiento** bajo US$ 10 000 ("pitufeo"). El ranking comercial esconde el mayor riesgo. |
| C10 · operaciones atípicas | Una regla simple ("5 veces el promedio") genera falsos positivos y no detecta el fraccionamiento, donde cada operación por separado parece normal. |
| Validación de features | Cada perfil inusual se separa con **una feature distinta** (`ratio_cerca_umbral` 0,754 frente a 0,004; `ratio_cuentas_terceros` 0,646 frente a 0,000; `ratio_nocturno` 0,651 frente a 0,009). Hace falta un **modelo multivariable**. |

**Modelo de IA.** Un enfoque híbrido:

- **Isolation Forest** (no supervisado), para detectar comportamientos raros que no se conocían.
- **Gradient boosting** (supervisado), entrenado con las decisiones del back-office: las operaciones rechazadas por cumplimiento son los casos positivos.

Las features salen de las 8 de la Parte 1: el modelo usa las 5 que describen **comportamiento** (sección 5.1), y en tiempo real se suman `operaciones_24h`, `cuentas_destino_30d` y `cuenta_compartida`. Las decisiones de los analistas vuelven como nuevas etiquetas y cierran el ciclo de aprendizaje.

# 2. Caracterización del problema

Las cifras salen de los datos de la Parte 1 (septiembre de 2026, el último mes completo) y de mediciones en PostgreSQL 18:

| Característica | Valor medido o estimado | Consecuencia para la tecnología |
|---|---|---|
| **Volumen de información** | 8,8 millones de filas y 1,6 GB en 21 meses. El estado "caliente" necesario para el scoring es mucho menor: unos 23 700 clientes activos en 90 días, con unas 12 operaciones cada uno en 120 días. | No es un problema de *big data* por volumen: el estado en línea cabe en memoria (≈ 150 MB). El histórico completo sí conviene llevarlo a un almacenamiento analítico barato. |
| **Frecuencia de generación** | ≈ 18 500 eventos de negocio por día (cotizaciones, operaciones, comprobantes y cambios de estado). Pico de 2 532 por hora y de **73 por minuto**. | Flujo continuo de eventos pequeños, ideal para *streaming*. |
| **Crecimiento** | Las operaciones diarias pasaron de 283 (enero de 2025) a 2 632 (septiembre de 2026): **9,3 veces en 20 meses**. | El diseño debe aguantar al menos 10 veces más sin rediseño: ≈ 185 000 eventos por día y picos de unos 12 por segundo. |
| **Tipos de datos** | Eventos estructurados (JSON), series de tiempo (ventanas por cliente, tasas cada 5 min), relaciones tipo grafo (cuentas que comparten varios clientes) y archivos (comprobantes en S3). | Las estructuras que necesita el scoring (contadores por ventana, conjuntos y rankings) no son tablas normalizadas. |
| **Necesidad de tiempo real** | El puntaje debe existir **antes** de que el analista abra la operación. La mediana de validación es de 15 a 33 minutos (C4), pero la cola se refresca continuamente y el riesgo debe estar listo de inmediato. | Scoring síncrono al cargar el comprobante, y ventanas actualizadas en segundos. |
| **Latencia esperada** | Lectura de features ≤ 5 ms (p99); scoring completo ≤ 60 ms adicionales a la API. | Se necesita una lectura por clave con costo **independiente del historial**. |
| **Patrón de lectura y escritura** | Escritura: un incremento por evento (muchas escrituras pequeñas). Lectura: el estado completo de **un** cliente por clave, sin joins. | Patrón clave–valor de acceso puntual, no relacional. |
| **Escalabilidad** | Horizontal por cliente: los clientes son independientes entre sí, salvo la cuenta compartida. | Particionar por `id_cliente`: shards en Redis y clave del mensaje (partición) en Kafka. |
| **Consultas predominantes** | "¿Cuántas operaciones hizo X en 24 h / 30 días?", "¿cuántas cerca del umbral?", "¿cuántas cuentas destino distintas?", "¿cuántos clientes envían a esta cuenta?", "dame las 50 operaciones más riesgosas". | Ventanas deslizantes, conteos y rankings: operaciones nativas de Redis (`ZCOUNT`, `HMGET`, `SCARD`, `ZREVRANGE`). |

## 2.1 ¿Por qué no calcular las features en PostgreSQL en cada evento?

Se midió la vista `v_features_cliente` de la Parte 1, ya con el índice `idx_operacion_cliente_fecha` de la optimización O1 (`06_parte2_caracterizacion.sql`, mediana de 5 corridas):

<div class="metricas">

| Cálculo de features en PostgreSQL | Operaciones del cliente | Tiempo |
|---|---|---|
| Cliente típico (CLI-06EZN7) | 26 | 6,1 ms |
| Cliente con fraccionamiento (CLI-ZYCHEZ) | 2 809 | **257,4 ms** (42 veces más) |
| Todos los clientes (batch) | 35 438 clientes | 5,5 s |

</div>

Los tiempos son con **caché fría**: el equipo tenía poca memoria libre, así que PostgreSQL leyó parte de los datos del disco (por ejemplo, 6 258 de 34 944 páginas para CLI-ZYCHEZ). Con la caché caliente los tiempos bajan, pero el cliente con más historial sigue siendo muchas veces más lento que el típico, porque el trabajo crece con el historial.

El resultado es claro:

- **El costo de PostgreSQL crece con el historial del cliente, y los clientes más riesgosos son justamente los que tienen más historial.** Hacen 10 operaciones diarias, y cada una obligaría a agregar 2 800 filas con joins a cotización y tasa.
- **Ese trabajo compite por CPU y caché** con las transacciones de negocio en la misma base.
- **Como cálculo batch nocturno funciona muy bien** (5,5 s para todos los clientes), y por eso se mantiene para el perfil estable.

Lo que falta es un almacenamiento donde el estado de cada cliente se **mantenga actualizado de forma incremental** y se lea en un tiempo constante.

# 3. Selección de tecnología

## 3.1 Tecnología elegida: Redis (Amazon ElastiCache) como feature store en línea

Se complementa con **Apache Kafka en Confluent Cloud** como bus de eventos (alimentado por CDC desde PostgreSQL con el conector Debezium) y **Databricks** sobre un Data Lake en S3 con **Delta Lake**, para la analítica histórica y el entrenamiento del modelo con **MLflow**.

| Pregunta | Respuesta |
|---|---|
| **Qué problema resuelve** | Servir el estado reciente de cada cliente (ventanas de 24 h, 30 y 90 días, cuentas destino, cuenta compartida, perfil) en menos de 1 ms, actualizándolo con cada evento en tiempo constante. Además mantiene la cola de revisión ordenada por riesgo. |
| **Por qué fue seleccionada** | Sus estructuras nativas calzan exactamente con las consultas del caso: *sorted sets* para las ventanas por tiempo y el ranking de riesgo, *hashes* para contadores diarios y perfil, *sets* para relaciones cuenta–clientes y TTL para la caducidad. Además es un servicio administrado en AWS, donde ya está el resto de NexoCambio. |
| **Ventajas para el caso** | Latencia submilisegundo estable; `HINCRBY`/`ZADD` atómicos y scripts Lua para actualizar varias claves juntas; *pipelining* (todas las features en un viaje de red); escalamiento horizontal por shards con *hash tags* por cliente; el estado de hoy (≈ 150 MB) y el de 10 veces más (≈ 1,5 GB) caben en un nodo pequeño. |
| **Limitaciones** | Los datos viven en memoria, así que el costo por GB es alto y no sirve para el histórico. No hay joins ni consultas ad hoc: cada pregunta nueva exige diseñar una estructura nueva. La durabilidad es más débil que la de PostgreSQL (snapshots, no transacciones con WAL síncrono). La consistencia con PostgreSQL es eventual, unos segundos vía CDC. |
| **Cómo se complementa con PostgreSQL** | PostgreSQL sigue siendo el **sistema de registro**: todas las escrituras de negocio van ahí. Redis solo guarda **datos derivados y reconstruibles**: si se pierde, se repuebla desde PostgreSQL (job nocturno) y Kafka (7 días de retención). El scoring nunca modifica el estado de una operación; la decisión la registra el analista en `historial_estado`. |

## 3.2 Alternativas evaluadas

| Alternativa | Qué ofrecía | Por qué no fue la principal |
|---|---|---|
| **Solo PostgreSQL** (vistas materializadas o tablas de agregados) | Una sola tecnología, consistencia fuerte | Las vistas materializadas se recalculan completas (5,5 s) y no por evento. Las tablas de agregados por trigger agregan escrituras a cada transacción del núcleo y bloqueos en clientes muy activos. |
| **Amazon DynamoDB** (ya se usa en el proyecto de Cloud) | Clave–valor serverless, latencia de un dígito en ms, alta durabilidad | Es una alternativa válida y más barata con poco tráfico. Pero no tiene *sorted sets* ni conjuntos con cardinalidad, así que las ventanas deslizantes y el ranking de riesgo exigen más lógica en la aplicación y más lecturas. Se deja como plan B si se prioriza lo serverless. |
| **TimescaleDB / InfluxDB** | Series de tiempo con agregados continuos | Resuelve bien las ventanas, pero agrega otra base de disco con latencia de milisegundos. Las tasas de referencia ya se resuelven en PostgreSQL con índices BRIN (Parte 1, O3). |
| **Neo4j** | Grafos: redes de cuentas compartidas y "mulas" | Muy útil para *investigar* redes en fase 2. Para el scoring en línea basta el `SCARD` sobre el set de la cuenta. |
| **Amazon Kinesis** en lugar de Kafka | Streaming administrado y nativo de AWS, integrado con Lambda y Firehose | Equivalente en función y algo más barato con poco tráfico. Se eligió **Kafka en Confluent Cloud** porque también es administrado (no se operan brokers) y ofrece un **conector administrado de Debezium** para el CDC desde PostgreSQL, y Databricks lee sus topics directamente con Structured Streaming. Además tiene Schema Registry para el contrato de eventos, retención configurable con relectura por *offset* y es la plataforma de streaming que se trabaja en el curso. |
| **Athena/Glue + SageMaker** en lugar de Databricks | Servicios nativos de AWS para consultar el Data Lake y entrenar modelos | Funcionan, pero son tres servicios que se integran por separado. **Databricks** reúne en una sola plataforma la ingesta desde Kafka, las tablas Delta (con transacciones y versiones sobre S3), Spark SQL para preparar las features y MLflow para versionar los modelos. Además es la plataforma de analítica que se trabaja en el curso. Su limitación es el costo del cómputo, que se acota con clusters que se apagan solos y jobs nocturnos. |
| **SageMaker Feature Store** | Feature store administrado (en línea y fuera de línea) | Buena opción a futuro. Hoy no ofrece las ventanas deslizantes ni el ranking de cola que necesita el caso, y su almacenamiento en línea es más caro por lectura. |

# 4. Modelo de datos NoSQL

El detalle completo está en `modelo_nosql.pdf`. El principio central es **modelar por consulta**: todas las claves de un cliente comparten el *hash tag* `{id_cliente}`, así que viven en el mismo shard y se leen en un *pipeline* o se actualizan juntas con un script Lua.

| Clave | Tipo | Para qué | Feature que resuelve |
|---|---|---|---|
| `cli:{id}:perfil` | Hash | Atributos estables y features batch (desde `v_features_cliente`) | es_pep, antigüedad, ratio_rechazo, monto promedio, última operación |
| `cli:{id}:diario` | Hash | Contadores por día: `n:`, `usd:`, `umbral:`, `noct:`, `terc:` + AAAAMMDD | operaciones_30d, ratio_cerca_umbral_90d, variacion_monto_30d, ratio_nocturno, ratio_cuentas_terceros |
| `cli:{id}:ops24h` | Sorted set | Operaciones de los últimos 7 días (score = instante) | operaciones_24h (velocidad) |
| `cli:{id}:destinos` | Sorted set | Cuentas destino (score = último uso) | cuentas_destino_30d |
| `cta:{hash}:clientes` | Set | Clientes que envían a una misma cuenta | cuenta_compartida (red de "mulas") |
| `op:{codigo}:riesgo` | Hash + TTL | Score, nivel, motivos y versión del modelo | Explicación para el analista |
| `cola:riesgo` | Sorted set | Operaciones pendientes ordenadas por riesgo | Cola del back-office |

Ejemplo del perfil y de los contadores diarios de un cliente:

```
HSET cli:{41768}:perfil  tipo_cliente persona  es_pep 0  antiguedad_dias 412  ratio_rechazo 0.042
                         monto_promedio_usd_90d 1489.20  ultima_operacion 1792623600000
HINCRBY cli:{41768}:diario n:20261021 1          HINCRBYFLOAT cli:{41768}:diario usd:20261021 9850.00
HINCRBY cli:{41768}:diario umbral:20261021 1     ZADD cli:{41768}:ops24h 1792608120000 "NX-7KQ2M9TA|9850.00"
```

Vector de features que arma el scoring y que, con la decisión del analista, se guarda en el Data Lake para reentrenar:

```json
{
  "codigo_operacion": "NX-7KQ2M9TA", "id_cliente": 41768,
  "features": { "operaciones_24h": 9, "operaciones_30d": 41, "ratio_cerca_umbral_90d": 0.92,
                "cuentas_destino_30d": 3, "cuenta_compartida": 1, "ratio_rechazo": 0.042,
                "variacion_monto_30d": 1.04, "ratio_nocturno": 0.00 },
  "resultado": { "score": 0.87, "nivel": "ALTO", "modelo": "v3.2" },
  "etiqueta":  { "decision_backoffice": "Rechazada" }
}
```

**Diferencias con el modelo relacional:**

- **Desnormalizado y orientado a la consulta:** una feature, una clave.
- **Sin integridad referencial:** la garantiza PostgreSQL.
- **Contadores pre-agregados en vez de filas de detalle.**
- **Caducidad explícita:** TTL y poda.
- **Sin datos personales:** solo IDs internos y hashes de cuenta.

# 5. Arquitectura propuesta

El diagrama completo, con la tabla de flujos, el diagrama de secuencia y el presupuesto de latencia, está en `arquitectura.pdf`.

<div class="diagrama"><svg viewBox="0 20 1400 640" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI, Arial, sans-serif" font-size="13">
<defs><marker id="f" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#44505c"/></marker></defs>
<g fill-opacity="1" stroke="#c9d2da">
<rect x="20" y="60" width="190" height="410" rx="10" fill="#f4f6f8"/>
<rect x="235" y="60" width="240" height="410" rx="10" fill="#f4f6f8"/>
<rect x="495" y="60" width="265" height="410" rx="10" fill="#eaf1f8"/>
<rect x="775" y="60" width="240" height="410" rx="10" fill="#fdf3e7"/>
<rect x="1035" y="60" width="345" height="410" rx="10" fill="#fbecec"/>
<rect x="20" y="500" width="1360" height="150" rx="10" fill="#edf6ef"/>
</g>
<g font-weight="600" fill="#5a6675" font-size="12.5">
<text x="115" y="82" text-anchor="middle">APLICACIONES CONSUMIDORAS</text>
<text x="355" y="82" text-anchor="middle">APIs · AWS</text>
<text x="627" y="82" text-anchor="middle">DATOS TRANSACCIONALES</text>
<text x="895" y="82" text-anchor="middle">PROCESAMIENTO EN TIEMPO REAL</text>
<text x="1207" y="82" text-anchor="middle">FEATURE STORE EN LÍNEA</text>
<text x="40" y="522">ANALÍTICA Y MACHINE LEARNING (BATCH) · DATABRICKS</text>
</g>
<g stroke="#44505c" stroke-width="1.6" fill="none" marker-end="url(#f)">
<path d="M190,125 L255,122"/>
<path d="M190,235 C228,235 225,132 255,130"/>
<path d="M355,145 L355,175"/>
<path d="M455,195 L520,160"/>
<path d="M455,228 L565,275"/>
<path d="M355,245 L355,335"/>
<path d="M455,358 L1080,322"/>
<path d="M1080,352 L455,388"/>
<path d="M670,118 L790,112"/>
<path d="M895,132 L895,160"/>
<path d="M895,210 L895,240"/>
<path d="M1000,265 L1080,280"/>
<path d="M1000,185 L1025,185 L1025,587 L962,587"/>
<path d="M790,587 L742,587"/>
<path d="M545,205 L545,538"/>
<path d="M560,587 L502,587"/>
<path d="M330,587 L292,587"/>
<path d="M200,555 L300,407"/>
<path d="M600,95 L600,42 L1220,42 L1220,228" stroke-dasharray="6 4"/>
</g>
<g font-size="12" fill="#1d2733">
<text x="468" y="224">1 · SQL ACID</text>
<text x="362" y="296">2 · ¿riesgo?</text>
<text x="362" y="311" fill="#5a6675">(síncrono)</text>
<text x="770" y="326" text-anchor="middle">3 · lee features en pipeline (&lt; 5 ms)</text>
<text x="770" y="392" text-anchor="middle">4 · score, motivos y cola priorizada por riesgo</text>
<text x="700" y="106">5 · WAL</text>
<text x="902" y="230">6 · eventos</text>
<text x="1000" y="258" font-size="10">ZADD · HINCRBY</text>
<text x="1030" y="455">7 · histórico</text>
<text x="552" y="440">8 · export nocturno</text>
<text x="552" y="455" fill="#5a6675">v_features_cliente</text>
<text x="160" y="480">9 · despliegue</text>
<text x="905" y="37" text-anchor="middle" fill="#5a6675">perfil batch nocturno → HSET cli:{id}:perfil</text>
</g>
<g stroke="#44505c" stroke-width="1.3">
<rect x="40" y="100" width="150" height="50" rx="6" fill="#fff"/>
<rect x="40" y="210" width="150" height="50" rx="6" fill="#fff"/>
<rect x="255" y="100" width="200" height="45" rx="6" fill="#fff"/>
<rect x="255" y="175" width="200" height="70" rx="6" fill="#fff"/>
<rect x="255" y="335" width="200" height="70" rx="6" fill="#fff" stroke="#b03a3a" stroke-width="2"/>
<rect x="790" y="92" width="210" height="40" rx="6" fill="#fff"/>
<rect x="790" y="160" width="210" height="50" rx="6" fill="#fff" stroke="#c46a12" stroke-width="2"/>
<rect x="790" y="240" width="210" height="50" rx="6" fill="#fff"/>
<rect x="790" y="560" width="170" height="55" rx="6" fill="#fff"/>
<rect x="330" y="560" width="170" height="55" rx="6" fill="#fff"/>
<rect x="60" y="555" width="230" height="65" rx="6" fill="#fff" stroke="#2e7d4f" stroke-width="2"/>
</g>
<g stroke-width="2">
<path d="M520,105 v90 a75,10 0 0 0 150,0 v-90" fill="#fff" stroke="#0f5b78"/><ellipse cx="595" cy="105" rx="75" ry="10" fill="#dcebf4" stroke="#0f5b78"/>
<path d="M565,250 v55 a85,10 0 0 0 170,0 v-55" fill="#fff" stroke="#44505c" stroke-width="1.3"/><ellipse cx="650" cy="250" rx="85" ry="10" fill="#f1f3f5" stroke="#44505c" stroke-width="1.3"/>
<path d="M1080,240 v130 a140,12 0 0 0 280,0 v-130" fill="#fff" stroke="#b03a3a"/><ellipse cx="1220" cy="240" rx="140" ry="12" fill="#f6dede" stroke="#b03a3a"/>
<path d="M560,550 v75 a90,10 0 0 0 180,0 v-75" fill="#fff" stroke="#2e7d4f"/><ellipse cx="650" cy="550" rx="90" ry="10" fill="#dff0e4" stroke="#2e7d4f"/>
</g>
<g text-anchor="middle" fill="#1d2733">
<text x="115" y="122" font-weight="600">App web Angular</text><text x="115" y="138" font-size="11.5" fill="#5a6675">clientes</text>
<text x="115" y="232" font-weight="600">Back-office</text><text x="115" y="248" font-size="11.5" fill="#5a6675">analistas y supervisores</text>
<text x="355" y="128" font-weight="600">API Gateway</text>
<text x="355" y="203" font-weight="600">Servicios de negocio</text><text x="355" y="220" font-size="11.5" fill="#5a6675">cotizaciones · clientes</text><text x="355" y="234" font-size="11.5" fill="#5a6675">operaciones · back-office</text>
<text x="355" y="363" font-weight="600">Servicio de scoring</text><text x="355" y="380" font-size="11.5" fill="#5a6675">inferencia en línea</text><text x="355" y="394" font-size="11.5" fill="#5a6675">modelo en memoria</text>
<text x="595" y="140" font-weight="700" font-size="14">PostgreSQL</text><text x="595" y="158" font-size="11.5" fill="#5a6675">núcleo relacional · 15 tablas</text><text x="595" y="173" font-size="11.5" fill="#5a6675">ACID · sistema de registro</text>
<text x="650" y="282" font-weight="600">Amazon S3</text><text x="650" y="298" font-size="11.5" fill="#5a6675">comprobantes</text>
<text x="895" y="117" font-weight="600" font-size="12.5">CDC · conector Debezium</text>
<text x="895" y="181" font-weight="700">Apache Kafka</text><text x="895" y="198" font-size="11.5" fill="#5a6675">Confluent Cloud · clave id_cliente</text>
<text x="895" y="261" font-weight="600">Procesador de features</text><text x="895" y="278" font-size="11.5" fill="#5a6675">consumer group · incremental</text>
<text x="1220" y="282" font-weight="700" font-size="15">Redis (ElastiCache)</text><text x="1220" y="302" font-size="12" fill="#5a6675">feature store en línea</text><text x="1220" y="320" font-size="11.5" fill="#5a6675">perfil · ventanas deslizantes</text><text x="1220" y="336" font-size="11.5" fill="#5a6675">riesgo por operación · cola</text><text x="1220" y="352" font-size="11.5" fill="#5a6675">TTL · datos derivados</text>
<text x="875" y="584" font-weight="600">Structured Streaming</text><text x="875" y="600" font-size="11.5" fill="#5a6675">Kafka → Delta (bronze)</text>
<text x="650" y="585" font-weight="700">Delta Lake en S3</text><text x="650" y="602" font-size="11.5" fill="#5a6675">bronze · silver · gold</text>
<text x="415" y="584" font-weight="600">Spark SQL · notebooks</text><text x="415" y="600" font-size="11.5" fill="#5a6675">features históricas</text>
<text x="175" y="580" font-weight="700">MLflow</text><text x="175" y="597" font-size="11.5" fill="#5a6675">entrenamiento · validación</text><text x="175" y="611" font-size="11.5" fill="#5a6675">registro de modelos</text>
</g>
</svg></div>

**Recorrido de una operación:**

1. **Registro.** El cliente crea la operación y sube su comprobante. Los servicios de negocio la registran en **PostgreSQL** dentro de una transacción (operación + historial de estados), igual que en la Parte 1.
2. **Scoring síncrono.** La API llama al **servicio de scoring**. Este lee en un *pipeline* las features del cliente en **Redis** (≈ 1 ms), suma la operación actual, aplica el modelo cargado en memoria (≈ 10–20 ms) y guarda el score, los motivos y la posición en la cola de riesgo. Todo agrega menos de 60 ms a la respuesta.
3. **Eventos.** El **CDC** (conector Debezium de Confluent, que lee la replicación lógica de PostgreSQL) publica cada cambio confirmado en un topic de **Kafka**, con `id_cliente` como clave. La API no escribe en dos bases, así que no puede haber una operación en Redis que no exista en PostgreSQL.
4. **Actualización incremental.** El **procesador de features**, un *consumer group* de Kafka, consume los eventos en orden por cliente y actualiza los contadores y las ventanas en Redis con un script Lua atómico.
5. **Back-office.** Ve la cola ordenada por riesgo, con los motivos del modelo. La decisión se escribe en PostgreSQL (`historial_estado`) y, por CDC, se convierte en una **etiqueta** para el siguiente entrenamiento.
6. **Histórico y entrenamiento.** **Databricks** lee los topics de Kafka con Structured Streaming y guarda todos los eventos en tablas **Delta** sobre S3 (capa *bronze*). Cada noche recibe también `v_features_cliente`. Con **Spark SQL** se prepara el conjunto de entrenamiento (capas *silver* y *gold*) y **MLflow** registra cada entrenamiento con sus parámetros y métricas (precisión en el top-k de la cola, recall de ROS confirmados). La versión aprobada se despliega en el servicio de scoring.
7. **Perfil batch.** Cada noche, el mismo `v_features_cliente` (5,5 s para todos los clientes) reescribe `cli:{id}:perfil` en Redis.

## 5.1 Implementación: pipeline medallion y modelo en Databricks

La capa analítica se implementó con la **arquitectura medallion** en un solo notebook de Databricks (`notebooks/pipeline_medallion.py`), sobre tablas Delta:

| Capa | Tablas | Qué hace |
|---|---|---|
| **Bronze** | `bronze_operaciones`, `bronze_clientes`, `bronze_cuentas`, `bronze_etiquetas` | Guarda los extractos de PostgreSQL tal como llegan (918 479 operaciones, 50 000 clientes, 224 441 cuentas), con la fecha de carga y el archivo de origen |
| **Silver** | `silver_operaciones`, `silver_clientes`, `silver_operaciones_rechazadas` | Corrige tipos, quita duplicados y valida (monto positivo, estado válido, fecha anterior al corte); lo inválido va a cuarentena. Agrega si la cuenta destino es de un tercero y la hora local |
| **Gold** | `gold_features_cliente`, `gold_clientes_riesgo`, `gold_exposicion_riesgo`, `gold_reactivacion` | Las 8 features con Spark SQL, el riesgo de cada cliente, la exposición del negocio y los clientes a reactivar |

Bronze se carga **por lotes** desde extractos de PostgreSQL (`generador/exportar_bronze.py`); en producción se llenaría desde los topics de Kafka con Structured Streaming, sin cambiar silver ni gold.

**Las mismas features en tres tecnologías.** `gold_features_cliente` replica en Spark SQL la vista `v_features_cliente` de la Parte 1. Para comprobarlo se compararon las sumas de control de las 8 features (cantidad de valores no nulos y suma) en los 35 438 clientes: **son idénticas a las de PostgreSQL** (`resultados/09_bronze_y_control_postgresql.txt` y `09_medallion_resultados.txt`). En Redis, la demo también reproduce exactamente las features de cada cliente (paso 5 de la demo). Es la garantía contra el *training-serving skew*: se entrena y se predice con lo mismo.

**El modelo.** Sobre `gold_features_cliente` se entrenó un **Isolation Forest**. Es **no supervisado**: nunca vio las etiquetas. Las 492 etiquetas de anomalías inyectadas (1,39 % de los clientes) se usaron solo para medir el resultado.

**El modelo usa solo las 5 features de comportamiento** (ratios de rechazo, cercanía al umbral, cuentas de terceros, variación del monto y actividad nocturna). Una primera versión usaba también las 3 de tamaño y actividad (operaciones en 30 días, ticket y recencia), y marcaba como riesgo ALTO a **59 de los 94 clientes grandes legítimos** que están entre los 100 más activos: confundía "cliente grande" con "cliente raro". Sin esas features, el modelo encuentra más casos inusuales y **no marca a ninguno** de esos clientes. El criterio de negocio es juzgar **cómo opera** el cliente, no **cuánto opera**.

La pregunta de negocio es: **si el back-office revisa solo el 2 % de clientes con mayor score (709), ¿cuántos casos inusuales encuentra?** Se compara con una regla simple de una sola feature, como las de la Parte 1:

<div class="metricas">

| Método | Clientes revisados | Casos encontrados | Precisión | Recall |
|---|---|---|---|---|
| Revisión al azar (referencia) | 709 | ≈ 10 | 1,4 % | 2,0 % |
| Regla: `ratio_cerca_umbral_90d` ≥ 0,5 | 173 | 160 | 92,5 % | 32,5 % |
| Isolation Forest con las 8 features (primera versión) | 709 | 329 | 46,4 % | 66,9 % |
| **Isolation Forest, solo comportamiento (top 2 %)** | **709** | **339** | **47,8 %** | **68,9 %** |

</div>

| Perfil inusual | Clientes | Detecta el modelo | Detecta la regla |
|---|---|---|---|
| Fraccionamiento (pitufeo) | 160 | 100 % | 100 % |
| Actividad nocturna | 91 | 94,5 % | 0 % |
| Multicuenta (cuentas de terceros) | 119 | 73,1 % | 0 % |
| Pico de montos | 122 | 4,9 % | 0 % |

Además, el modelo obtuvo un ROC AUC de 0,922 (0,896 en la primera versión) y no marca a ninguno de los 94 clientes grandes legítimos.

**Interpretación.**

- **Revisando el 2 % de los clientes, el modelo encuentra más de dos de cada tres casos inusuales**, 34 veces más que una revisión al azar. La regla es muy precisa, pero solo ve el fraccionamiento; el modelo detecta tres tipos de comportamiento sin que nadie le diga qué buscar. Es la evidencia práctica de que hace falta un modelo multivariable.
- **El pico de montos casi no se detecta, y eso confirma la arquitectura.** Con las features batch, el perfil "pico" se parece demasiado al de un cliente normal: la mediana de `variacion_monto_30d` es 1,01, igual que la de los clientes normales. Un pico se reconoce comparando **la operación actual** con el perfil del cliente, y eso es justo lo que hace el scoring en línea con Redis (paso 2 del recorrido): suma la operación actual a las features del cliente y agrega `operaciones_24h`.
- **El modelo prioriza, no decide.** El 47,8 % de precisión significa que más de la mitad de los clientes señalados son normales. Por eso la decisión final sigue siendo del analista, y esas decisiones son las etiquetas con las que se entrenaría el modelo supervisado de la fase 3.

**Exposición del negocio (`gold_exposicion_riesgo`).** Con el riesgo de cada cliente se mide qué parte del negocio de los últimos 90 días pasa por clientes inusuales:

<div class="metricas">

| Riesgo | Clientes | Volumen procesado | % del volumen | Spread cobrado | % del spread |
|---|---|---|---|---|---|
| **ALTO** (top 2 %) | 438 | US$ 75,4 millones | **16,9 %** | US$ 277 616 | **16,2 %** |
| MEDIO (hasta el top 10 %) | 2 398 | US$ 100,8 millones | 22,6 % | US$ 345 719 | 20,2 % |
| NORMAL | 20 570 | US$ 270,5 millones | 60,6 % | US$ 1 091 800 | 63,7 % |

</div>

**Uno de cada seis dólares que mueve NexoCambio viene de clientes con comportamiento inusual**, entre ellos sus dos mayores clientes (CLI-ZYCHEZ y CLI-XKLBXW, que fraccionan) y ninguno de sus clientes grandes legítimos. Es ingreso expuesto a sanciones de la UIF y a que los bancos cierren las cuentas de la empresa. Con este dato, la gerencia puede aplicar debida diligencia reforzada a 438 clientes en vez de a 35 438.

Las cifras salen de `resultados/09_medallion_resultados.txt`, la ejecución local del notebook con PySpark 4.0. Una primera versión del modelo, sin la capa medallion, ya se había ejecutado en **Databricks Free Edition** con resultados idénticos a los locales; allí el notebook registra además el modelo en MLflow y escribe las tablas Delta.

## 5.2 Segundo uso de la misma arquitectura: recuperar cotizaciones abandonadas

La plataforma no solo protege el negocio: también puede hacerlo crecer. Un cliente registrado que cotiza recibe una **tasa garantizada por 5 minutos**; si no opera en ese tiempo, la venta suele perderse. Se midió cuánto ingreso se pierde así en los últimos 90 días (`sql/08_oportunidades_ingreso.sql`):

<div class="metricas">

| Cotizaciones de clientes registrados que no se convirtieron | Casos | Spread no cobrado |
|---|---|---|
| Operó en los 30 minutos siguientes (volvió a cotizar) | 2 880 cotizaciones | — |
| Operó entre 30 minutos y 24 horas después | 40 344 cotizaciones | — |
| **No operó en 24 horas: intención perdida** (un caso por cliente y día) | **110 667 casos · 1 243 al día** | **US$ 863 592** |
| Referencia: spread cobrado en los mismos 90 días | | US$ 1 715 135 |

</div>

Las cotizaciones seguidas de una operación en las 24 horas siguientes no cuentan como pérdida: el cliente solo comparó o se le venció la tasa y volvió. Aun así, **la intención perdida equivale a la mitad del ingreso cobrado**. Son 22 679 clientes distintos con un ticket promedio de US$ 2 015, y 10 801 de esos casos superan los US$ 5 000. Recuperar el 10 % de esos casos equivaldría a unos **US$ 29 000 de spread al mes**, cerca del 5 % del ingreso mensual (US$ 593 540 en septiembre).

**Cómo funciona.** La acción solo sirve si llega mientras el cliente todavía está decidiendo, así que tiene que ser en tiempo real. Por eso reutiliza la arquitectura de la sección 5 (detalle en `arquitectura.pdf` y `modelo_nosql.pdf`, sección 9):

1. Cada cotización llega por el topic `nexocambio.cotizaciones` y el procesador la registra en Redis en un *sorted set* ordenado por vencimiento.
2. Si llega la operación de esa cotización, sale de la lista.
3. Si vence sin operación, el procesador lee las features del cliente, calcula su **score de riesgo** y decide: mantener la tasa 5 minutos más, o, si cotizó entre US$ 4 000 y 4 999, ofrecerle la tasa preferencial si sube a US$ 5 000.
4. **A un cliente de riesgo ALTO no se le ofrece ningún incentivo.** El mismo modelo que protege al negocio filtra a quién se le hace una oferta comercial.

En la demo, el ciclo completo (cotización, vencimiento, consulta de riesgo y decisión) toma unos 30–50 ms después de que vence la tasa. Las cifras usan datos ficticios: las tasas de conversión las definió el generador de datos, así que muestran el método y el orden de magnitud, no una predicción.

## 5.3 Tercer uso, en batch: clientes a reactivar

La tabla `gold_reactivacion` del pipeline medallion responde una pregunta comercial que no necesita tiempo real: **¿qué clientes frecuentes se están enfriando y cuánto valían?** Es la lógica de la consulta C9 de la Parte 1, llevada a una tabla que el área comercial recibe cada semana.

Un cliente frecuente (5 operaciones procesadas o más) está **en riesgo de abandono** cuando lleva sin operar más del doble de su intervalo habitual y al menos 14 días, pero menos de 120. El mínimo de 14 días evita alertar por un cliente que opera a diario y no lo hizo un fin de semana.

<div class="metricas">

| Segmento | Clientes | Días sin operar (promedio) | Spread mensual cuando estaban activos |
|---|---|---|---|
| Activo | 14 614 | 9 | US$ 577 690 |
| **En riesgo** | **4 991** | **58** | **US$ 145 520** |
| Abandono (más de 120 días) | 7 465 | 294 | US$ 240 057 |

</div>

Los clientes en riesgo generaban **US$ 145 520 de spread al mes**, el 25 % del ingreso mensual de septiembre. La lista se ordena por ese valor, así que el área comercial empieza por los que más aportaban. Recuperar a uno de cada cinco equivaldría a unos US$ 29 000 al mes. **De los 4 991, se excluye a los 28 de riesgo ALTO**: la misma regla de la sección 5.2, no premiar al cliente riesgoso. Las cifras coinciden exactamente entre el notebook (Spark) y `sql/08_oportunidades_ingreso.sql` (PostgreSQL).

Con esto, la plataforma de datos sirve a tres decisiones con los mismos datos y el mismo modelo: **a quién revisar** (cumplimiento, en tiempo real), **a quién rescatar en el momento** (cotizaciones, en tiempo real) y **a quién llamar esta semana** (reactivación, en batch).

# 6. Comparación entre PostgreSQL y Redis

| Criterio | PostgreSQL | Redis (ElastiCache) |
|---|---|---|
| **Modelo** | Relacional: tablas normalizadas (3FN), 15 entidades | Clave–valor con estructuras: hash, sorted set, set, string |
| **Esquema** | Estricto y declarado (tipos, NOT NULL, CHECK) | Sin esquema: la estructura la define la aplicación (convención de claves) |
| **Integridad** | PK, FK, UNIQUE, CHECK (29 reglas probadas en la Parte 1) | Ninguna: la aplicación es responsable |
| **JOIN** | Muy adecuado (la vista `v_operacion` une 4 tablas) | No existe: los datos se pre-combinan al escribir |
| **Transacciones** | ACID completas, aislamiento configurable | Atómicas por comando, `MULTI`/`EXEC` y scripts Lua, sin rollback |
| **Durabilidad** | Alta: WAL y commit síncrono | Media: snapshots o AOF; aquí los datos son reconstruibles |
| **Consistencia con la fuente** | Es la fuente de verdad | Eventual (≈ segundos vía CDC) |
| **Latencia típica** | Milisegundos; crece con el volumen agregado (6 a 257 ms en las features, con caché fría) | Submilisegundo y constante (O(1) – O(log n) por comando) |
| **Consultas** | SQL arbitrario, ad hoc, analítico (CTE, ventanas, ROLLUP) | Solo las que se modelaron; sin consultas ad hoc |
| **Caducidad de datos** | Manual (DELETE, particiones) | Nativa (TTL por clave, poda por score) |
| **Escalabilidad horizontal** | Posible (réplicas de lectura, particionamiento, Citus), pero compleja para escrituras | Alta: shards por slot de hash, con escalamiento en línea |
| **Costo de almacenamiento** | Bajo (disco); apto para años de histórico | Alto (RAM); solo para el estado reciente |
| **Caso principal en NexoCambio** | Núcleo transaccional, auditoría, reportes de negocio, cálculo batch de features | Feature store en línea, ventanas deslizantes, cola de riesgo |

# 7. ¿Por qué usar ambas tecnologías? Polyglot Persistence

**Polyglot Persistence** significa usar el almacenamiento más adecuado para cada **patrón de acceso** dentro de un mismo sistema, en vez de forzar una sola tecnología para todo. En NexoCambio hay dos patrones con requisitos opuestos.

**1. Registrar el negocio.** Clientes, cotizaciones, operaciones y decisiones exigen **integridad y transacciones**:

- una cotización no puede usarse dos veces;
- las cuentas deben pertenecer al cliente;
- una operación procesada no puede volver a "En proceso";
- todo debe ser auditable por años para la UIF.

Eso es exactamente lo que PostgreSQL garantiza de forma declarativa. Redis no podría hacerlo: no tiene FK, CHECK ni durabilidad transaccional.

**2. Responder "¿qué tan raro es esto?" en milisegundos.** Exige **estado precalculado por cliente, actualizado de forma incremental y leído en tiempo constante**. Hacerlo en PostgreSQL significaría agregar el historial en cada evento: 257 ms para los clientes más riesgosos, con un costo que crece con el tiempo y compite con las transacciones del núcleo. Redis lo resuelve con estructuras nativas en menos de 1 ms.

**Reemplazar una por otra sería un error en cualquier dirección:**

- **Todo en Redis:** se pierde la integridad, las consultas ad hoc y el histórico barato. Además, NexoCambio quedaría sin un sistema de registro confiable.
- **Todo en PostgreSQL:** se sobrecarga el núcleo con trabajo analítico por evento y la latencia del scoring empeora a medida que el negocio crece.

**Cómo conviven sin problemas:**

- **Una sola fuente de verdad.** Solo PostgreSQL recibe escrituras de negocio. Redis y el Data Lake se alimentan por **CDC**, nunca por doble escritura desde la API.
- **Datos derivados y reconstruibles.** Si Redis se pierde, se reconstruye; si Redis no responde, el scoring se degrada a calcular en PostgreSQL con el índice O1.
- **Las mismas features en todos lados.** La lógica de las features se definió una vez en SQL (Parte 1). Se usa en batch (perfil nocturno y entrenamiento) y se replica de forma incremental en línea, validando periódicamente que ambas coincidan.

NexoCambio ya practica esta idea: en el proyecto de Cloud Computing combina DynamoDB (operación serverless) y S3 (archivos). Esta Parte 2 la lleva al terreno de la IA, con **PostgreSQL para la verdad, Redis para la velocidad y S3 para la memoria de largo plazo**.

# 8. Hoja de ruta, riesgos y conclusiones

## 8.1 Implementación por fases

| Fase | Alcance | Valor |
|---|---|---|
| 1 · Batch | `v_features_cliente` nocturna → Isolation Forest en Databricks → ranking diario de clientes para cumplimiento | Ya probado (sección 5.1): con el 2 % de revisión encuentra el 68,9 % de los casos inusuales |
| 2 · Tiempo real | CDC → Kafka → Redis; scoring síncrono al cargar el comprobante; cola por riesgo; recuperación de cotizaciones abandonadas (sección 5.2) | Prioriza la revisión operación por operación y recupera ventas que se pierden en 5 minutos |
| 3 · Aprendizaje continuo | Delta Lake + MLflow en Databricks; gradient boosting con las etiquetas del back-office; monitoreo de deriva de features | El modelo mejora con cada decisión |
| 4 · Investigación | Grafo de cuentas compartidas (Neo4j) para redes de "mulas" | Análisis de redes, no solo de clientes individuales |

## 8.2 Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Diferencia entre las features en línea y las de entrenamiento (*training-serving skew*) | Se guarda el mismo vector de features que se usó al predecir, y se compara a diario contra `v_features_cliente` |
| Eventos duplicados o desordenados en Kafka | Clave del mensaje = id_cliente (misma partición, orden por cliente) y último *offset* aplicado guardado en el perfil (idempotencia) |
| Caída de Redis | Réplica en otra zona; modo degradado calculando en PostgreSQL; la operación nunca se bloquea |
| Sesgo del modelo o falsos positivos | El modelo **prioriza**, no rechaza: la decisión final es siempre humana y queda auditada en `historial_estado` |
| Datos personales fuera del núcleo | Redis y el Data Lake solo guardan IDs internos y hashes; cifrado en tránsito y en reposo |

## 8.3 Conclusiones

1. **El caso de IA sale de los datos, no de una moda.** La Parte 1 mostró que el principal motivo de rechazo es el cumplimiento y que los mayores clientes fraccionan sus operaciones. Detectarlo a tiempo es el problema de negocio con más impacto.
2. **El problema no es de volumen sino de latencia y patrón de acceso:** 18 500 eventos por día y un estado en línea de ≈ 150 MB. Lo que PostgreSQL no hace bien es mantener ventanas por cliente con costo constante; con él, las features cuestan de 6 a 257 ms según el historial.
3. **Redis es la tecnología adecuada** porque sus estructuras (sorted sets, hashes, sets y TTL) son las mismas operaciones que piden las features. Con Kafka en Confluent Cloud (CDC) y Databricks (Delta Lake y MLflow) completa un ciclo de detección, decisión humana y reentrenamiento. La prueba del modelo lo respalda: revisando el 2 % de los clientes encuentra el 68,9 % de los casos inusuales, sin marcar a los clientes grandes legítimos.
4. **PostgreSQL no se reemplaza, se protege:** sigue siendo el sistema de registro, con su integridad, sus índices y sus consultas de negocio, mientras la carga de tiempo real se resuelve fuera de él. Eso es Polyglot Persistence aplicada con criterio.
5. **La misma plataforma protege el negocio y lo hace crecer.** Los eventos, las features y el score de riesgo que sirven a cumplimiento también permiten recuperar cotizaciones abandonadas en tiempo real (intención de compra equivalente a la mitad del spread cobrado) y reactivar a 4 991 clientes que generaban US$ 145 520 al mes. En los dos casos, el score de riesgo decide a quién no se le ofrece un incentivo.
