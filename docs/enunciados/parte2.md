# Enunciado · Parte 2

1. Arquitectura de datos para Ciencia de Datos e Inteligencia Artificial

En la segunda etapa, cada equipo deberá ampliar el caso desarrollado en la primera entrega.

Se deberá identificar un escenario de Ciencia de Datos o Inteligencia Artificial cuyas características de: volumen, velocidad, variedad, latencia, escalabilidad o patrón de acceso puedan beneficiarse de una tecnología de almacenamiento o procesamiento especializada complementaria al modelo relacional.

La finalidad no es reemplazar PostgreSQL, sino identificar cuándo una arquitectura especializada puede resultar más adecuada para un determinado problema.

2. Definición del caso de IA o Ciencia de Datos

El caso seleccionado deberá estar relacionado directamente con el negocio trabajado en la primera entrega.

Ejemplos:

| Empresa | Caso de IA / Ciencia de Datos |
|---|---|
| Betsson | Detección de patrones anómalos de apuestas |
| Teleticket | Sistema de recomendación de eventos |
| eToro | Análisis de relaciones entre usuarios y activos |
| Duolingo | Personalización de ejercicios |
| StockX | Búsqueda semántica de productos |

Otros ejemplos posibles:

- Sistemas de recomendación.
- Chatbots con RAG.
- Búsqueda semántica.
- Detección de anomalías.
- Análisis de comportamiento.
- Procesamiento de eventos en tiempo real.
- Motores de personalización.
- Sistemas de similitud.
- Detección de fraude.

3. Caracterización del problema

El equipo deberá describir las principales características del problema:

- Volumen estimado de información.
- Frecuencia de generación de datos.
- Tipos de datos involucrados.
- Necesidad de procesamiento en tiempo real.
- Latencia esperada.
- Patrón de lectura y escritura.
- Escalabilidad esperada.
- Tipo de consultas predominantes.

La selección de tecnología deberá derivarse de estas características.

4. Selección de tecnología

El equipo deberá seleccionar y justificar una tecnología complementaria.

Algunas alternativas son:

| Necesidad | Tecnología posible |
|---|---|
| Documentos | MongoDB / DynamoDB |
| Cache | Redis |
| Series temporales | TimescaleDB / InfluxDB |
| Grafos | Neo4j |
| Búsqueda | Elasticsearch / OpenSearch |
| Datos vectoriales | pgvector / Pinecone / Weaviate / Milvus / AI Search |
| Eventos / streaming | Kafka / Kinesis |
| Analítica masiva | BigQuery / Snowflake / Redshift / Databricks |

No es obligatorio utilizar alguna de estas tecnologías específicamente.

El equipo podrá proponer otra alternativa siempre que explique adecuadamente:

- Qué problema resuelve.
- Por qué fue seleccionada.
- Qué ventajas ofrece para el caso propuesto.
- Qué limitaciones presenta.
- Cómo se complementaría con la arquitectura relacional existente.

5. Modelo de datos NoSQL o especializado

El equipo deberá diseñar la estructura de datos asociada a la tecnología seleccionada.

Ejemplo: base documental

```json
{
  "usuario_id": 9281,
  "nombre": "Ana",
  "preferencias": {
    "musica": ["rock", "indie"],
    "ciudades": ["Lima"]
  },
  "eventos_vistos": [
    {
      "evento_id": 182,
      "fecha": "2026-10-01",
      "interaccion": "click"
    }
  ]
}
```

6. Arquitectura propuesta

Cada equipo deberá presentar obligatoriamente un diagrama de arquitectura.

El diagrama deberá representar, según corresponda:

- Aplicaciones consumidoras.
- APIs.
- Base de datos relacional.
- Sistemas de eventos.
- Procesamiento de datos.
- Data Lake o almacenamiento analítico.
- Pipelines de Machine Learning.
- Bases vectoriales.
- Sistemas de búsqueda.
- Servicios de inferencia.
- Herramientas NoSQL seleccionadas.

Ejemplo conceptual:

```
                APP WEB / MOBILE
                       |
                       v
                      API
                       |
             +---------+---------+
             |                   |
             v                   v
        PostgreSQL             Kafka
             |                   |
             |                   v
             |               Data Lake
             |                   |
             v                   v
       Datos negocio         ML Pipeline
                                  |
                                  v
                            Vector Database
                                  |
                                  v
                           Recommendation API
```

No será obligatorio implementar toda la arquitectura.

El objetivo es que el grupo sea capaz de explicar:

Qué tecnología utilizaría, para qué la utilizaría y por qué resulta adecuada para el problema.

7. Comparación entre tecnologías

Cada equipo deberá realizar una comparación entre PostgreSQL y la tecnología especializada seleccionada.

Ejemplo:

| Criterio | PostgreSQL | MongoDB |
|---|---|---|
| Modelo | Relacional | Documental |
| Esquema | Estructurado | Flexible |
| JOIN | Muy adecuado | Limitado |
| Transacciones | Excelente soporte | Disponible |
| Escalabilidad horizontal | Posible | Alta |
| Caso principal | Core transaccional | Información semiestructurada |

Finalmente deberán responder:

¿Por qué utilizar ambas tecnologías en lugar de reemplazar una por otra?

Se espera que los estudiantes comprendan el concepto de Polyglot Persistence, donde diferentes tecnologías pueden coexistir dentro de una arquitectura dependiendo de las características del problema.

8. Entregables

```
grupo_XX/
│
├── arquitectura.pdf
├── modelo_nosql.pdf
└── informe_final.pdf
```
