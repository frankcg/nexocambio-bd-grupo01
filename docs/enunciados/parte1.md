# Enunciado · Parte 1

1. Análisis de negocio, modelo relacional y explotación de datos

1.1. Análisis del negocio
El equipo deberá describir brevemente:

- Giro y modelo de negocio.
- Principales clientes o usuarios.
- Productos y/o servicios.
- Principales canales.
- Proceso de negocio seleccionado.
- Actores involucrados.
- Principales eventos o transacciones.
- Información relevante generada durante el proceso.
- Principales preguntas que el negocio podría responder utilizando datos.

El objetivo no es realizar una descripción extensa de la organización, sino proporcionar el contexto necesario para comprender el modelo de datos.

1.2. Modelado Entidad–Relación
Diseñar un modelo Entidad–Relación que represente adecuadamente el proceso seleccionado.

El modelo deberá incluir como mínimo:

- Entidades.
- Atributos.
- Claves primarias.
- Claves foráneas.
- Relaciones.
- Cardinalidades.
- Restricciones relevantes.
- Resolución adecuada de relaciones N.

El modelo deberá encontrarse, como mínimo, en Tercera Forma Normal (3FN), salvo que exista alguna decisión de desnormalización debidamente justificada.

Se deberán explicar brevemente las principales decisiones de diseño.

Como referencia, se recomienda trabajar con un modelo de aproximadamente 8 a 15 entidades, priorizando calidad y coherencia sobre cantidad.

1.3. Implementación en PostgreSQL
El modelo deberá ser implementado en PostgreSQL.

Como mínimo deberán utilizarse:

- CREATE SCHEMA
- CREATE TABLE
- PRIMARY KEY
- FOREIGN KEY
- UNIQUE
- CHECK
- NOT NULL
- INSERT INTO

Asimismo, deberán seleccionar correctamente los tipos de datos de cada atributo.

Los estudiantes podrán utilizar diferentes mecanismos para cargar información:

- Scripts INSERT INTO.
- Archivos CSV.
- Datos sintéticos.
- Datos públicos.
- Datos proporcionados por la organización seleccionada.

El conjunto de datos deberá ser suficientemente representativo para ejecutar las consultas y ejercicios de optimización solicitados posteriormente.

2. Consultas SQL orientadas al negocio
Cada equipo deberá desarrollar un mínimo de 8 consultas SQL que respondan preguntas relevantes del negocio.

Las consultas deberán presentar diferentes niveles de complejidad.

2.1. Consultas básicas e intermedias
Al menos dos consultas deberán utilizar conceptos como:

- WHERE
- ORDER BY
- GROUP BY
- HAVING
- funciones de agregación
- INNER JOIN
- LEFT JOIN

2.2. Consultas avanzadas
Al menos tres consultas deberán utilizar uno o más de los siguientes conceptos:

- Subconsultas.
- CTE.
- CASE.
- Funciones ventana.
- ROW_NUMBER.
- RANK.
- DENSE_RANK.
- LAG.
- LEAD.
- Acumulados.
- Comparaciones contra promedios.
- Análisis temporal.

Cada consulta deberá incluir:

- Pregunta de negocio.
- Consulta SQL.
- Resultado esperado.
- Breve interpretación del resultado.

3. Feature Engineering utilizando SQL
Cada equipo deberá diseñar un mínimo de 5 variables o features que potencialmente podrían utilizarse en un modelo de Machine Learning o solución de Inteligencia Artificial.

Cada feature deberá incluir:

- Nombre.
- Definición.
- Justificación.
- Consulta SQL utilizada para obtenerla.
- Posible uso dentro de un modelo de IA o Ciencia de Datos.

Ejemplo:

Para una plataforma de apuestas:

| Feature | Descripción |
|---|---|
| apuestas_30d | Número de apuestas realizadas durante los últimos 30 días |
| monto_promedio_apuesta | Monto promedio apostado por el usuario |
| dias_desde_ultima_apuesta | Días transcurridos desde la última apuesta |
| ratio_apuestas_ganadas | Proporción de apuestas ganadas |
| variacion_monto_3m | Variación del monto apostado durante los últimos tres meses |

4. Optimización de consultas e índices
Cada equipo deberá seleccionar al menos dos consultas relevantes desarrolladas anteriormente y analizar su rendimiento.

Para ello deberán utilizar: EXPLAIN y EXPLAIN ANALYZE

El análisis deberá identificar:

- Tipo de Scan utilizado.
- Costo estimado.
- Número de filas estimadas.
- Número de filas reales.
- Tiempo de planificación.
- Tiempo de ejecución.
- Operaciones más costosas.
- Posibles cuellos de botella.

Los estudiantes deberán posteriormente proponer al menos una optimización.

Por ejemplo:

```sql
CREATE INDEX idx_apuesta_cliente_fecha
ON apuestas(cliente_id, fecha_apuesta);
```

Luego deberán ejecutar nuevamente:

```sql
EXPLAIN ANALYZE
SELECT ...
```

y comparar los resultados.

Ejemplo de comparación:

| Métrica | Antes | Después |
|---|---|---|
| Tipo de acceso | Seq Scan | Index Scan |
| Execution Time | 86 ms | 8 ms |
| Filas evaluadas | 250,000 | 120 |
| Índice utilizado | No | Sí |

No se considerará que una optimización es correcta únicamente porque se haya creado un índice.

El equipo deberá explicar por qué el índice es adecuado para la consulta y demostrar su impacto mediante el plan de ejecución.

5. Entregables

```
grupo_XX/
│
├── informe.pdf
├── modelo_ER.pdf
│
├── sql/
│   ├── 01_schema.sql
│   ├── 02_tables.sql
│   ├── 03_data.sql
│   ├── 04_queries.sql
│   └── 05_indexes.sql
│
└── datos/
    └── dataset.csv
```
