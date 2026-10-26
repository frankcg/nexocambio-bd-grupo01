-- =============================================================================
-- NexoCambio · 05_indexes.sql
-- Optimización: cada caso muestra el plan estimado con EXPLAIN, mide la ejecución real
-- con EXPLAIN (ANALYZE, BUFFERS), crea un índice justificado por su patrón de acceso
-- y vuelve a medir.
--
-- El script empieza borrando los índices que crea, así que siempre parte del mismo
-- estado (solo los índices de PRIMARY KEY y UNIQUE). Para comparar con la caché
-- caliente, se ejecuta dos veces y se toma la segunda corrida.
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/05_indexes.sql
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path TO nexocambio;

DROP INDEX IF EXISTS idx_operacion_cliente_fecha, idx_operacion_cola_backoffice, idx_operacion_estado_fecha,
                     idx_cotizacion_fecha_btree, idx_cotizacion_fecha_brin, idx_operacion_fecha_brin;
ANALYZE operacion;
ANALYZE cotizacion;

-- Cliente de ejemplo: persona natural con actividad típica (26 operaciones en 90 días).
SELECT id_cliente AS cliente_demo FROM cliente WHERE codigo_cliente = 'CLI-06EZN7' \gset


-- #############################################################################
-- O1 · Historial de operaciones de un cliente en los últimos 90 días
-- Patrón: GET /operaciones (pantalla "Mis operaciones") y cálculo de features en
-- línea. Es la consulta más frecuente de la aplicación: una por cliente que entra.
-- #############################################################################
\echo '\n=========== O1 · EXPLAIN (plan estimado: no ejecuta la consulta) ==========='
EXPLAIN
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual,
       q.moneda_origen, q.moneda_destino, q.monto_origen, q.monto_destino
FROM operacion o
JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion
WHERE o.id_cliente = :cliente_demo
  AND o.fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
ORDER BY o.fecha_operacion DESC;

\echo '\n=========== O1 · ANTES (sin índice en operacion.id_cliente) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual,
       q.moneda_origen, q.moneda_destino, q.monto_origen, q.monto_destino
FROM operacion o
JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion
WHERE o.id_cliente = :cliente_demo
  AND o.fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
ORDER BY o.fecha_operacion DESC;

-- Índice compuesto: la igualdad (id_cliente) va primero y el rango (fecha_operacion)
-- después, en orden DESC, para que el índice entregue las filas ya ordenadas y el
-- plan no necesite un Sort. También cubre la FK operacion.id_cliente, que PostgreSQL
-- no indexa automáticamente.
CREATE INDEX idx_operacion_cliente_fecha ON operacion (id_cliente, fecha_operacion DESC);
ANALYZE operacion;

\echo '\n=========== O1 · DESPUÉS (idx_operacion_cliente_fecha) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual,
       q.moneda_origen, q.moneda_destino, q.monto_origen, q.monto_destino
FROM operacion o
JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion
WHERE o.id_cliente = :cliente_demo
  AND o.fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
ORDER BY o.fecha_operacion DESC;


-- #############################################################################
-- O2 · Cola de revisión del back-office
-- Patrón: GET /operaciones/admin; los analistas la refrescan constantemente.
-- De 918 mil operaciones solo unas 200 están pendientes: el estado es muy selectivo
-- pero está muy desbalanceado (el 87 % está "Procesada").
-- #############################################################################
\echo '\n=========== O2 · EXPLAIN (plan estimado: no ejecuta la consulta) ==========='
EXPLAIN
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual, c.codigo_cliente
FROM operacion o
JOIN cliente c ON c.id_cliente = o.id_cliente
WHERE o.estado_actual IN ('Pendiente de validación', 'En proceso')
ORDER BY o.fecha_operacion
LIMIT 50;

\echo '\n=========== O2 · ANTES (sin índice) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual, c.codigo_cliente
FROM operacion o
JOIN cliente c ON c.id_cliente = o.id_cliente
WHERE o.estado_actual IN ('Pendiente de validación', 'En proceso')
ORDER BY o.fecha_operacion
LIMIT 50;

-- Alternativa descartada: un índice completo sobre (estado_actual, fecha_operacion)
-- indexaría también las ~800 mil operaciones cerradas, que la cola nunca consulta.
-- Se crea solo para comparar su tamaño y luego se elimina.
CREATE INDEX idx_operacion_estado_fecha ON operacion (estado_actual, fecha_operacion);

-- Índice parcial: solo contiene las operaciones abiertas. Ocupa una fracción mínima
-- del índice completo, se mantiene pequeño aunque la tabla crezca y sus entradas salen
-- del índice cuando la operación se cierra.
CREATE INDEX idx_operacion_cola_backoffice ON operacion (fecha_operacion)
    WHERE estado_actual IN ('Pendiente de validación', 'En proceso');

\echo '\n=========== O2 · Tamaño: índice completo vs. parcial ==========='
SELECT indexrelname AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tamano
FROM pg_stat_user_indexes
WHERE indexrelname IN ('idx_operacion_estado_fecha', 'idx_operacion_cola_backoffice');

DROP INDEX idx_operacion_estado_fecha;
ANALYZE operacion;

\echo '\n=========== O2 · DESPUÉS (idx_operacion_cola_backoffice, parcial) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual, c.codigo_cliente
FROM operacion o
JOIN cliente c ON c.id_cliente = o.id_cliente
WHERE o.estado_actual IN ('Pendiente de validación', 'En proceso')
ORDER BY o.fecha_operacion
LIMIT 50;


-- #############################################################################
-- O3 · Embudo de conversión de un mes (septiembre 2026)
-- Patrón: reportes por rango de fechas sobre la tabla más grande (2 millones de
-- cotizaciones). Las cotizaciones se insertan en orden cronológico, así que la
-- columna fecha_cotizacion tiene correlación física 1,0 (pg_stats): candidata a BRIN.
-- #############################################################################
\echo '\n=========== O3 · Correlación física de fecha_cotizacion ==========='
SELECT attname, round(correlation::numeric, 4) AS correlacion
FROM pg_stats
WHERE schemaname = 'nexocambio' AND tablename = 'cotizacion' AND attname = 'fecha_cotizacion';

\echo '\n=========== O3 · EXPLAIN (plan estimado: no ejecuta la consulta) ==========='
EXPLAIN
SELECT q.modalidad, count(*) AS cotizaciones, count(o.id_operacion) AS operaciones
FROM cotizacion q
LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
GROUP BY q.modalidad;

\echo '\n=========== O3 · ANTES (sin índice en fecha_cotizacion) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT q.modalidad, count(*) AS cotizaciones, count(o.id_operacion) AS operaciones
FROM cotizacion q
LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
GROUP BY q.modalidad;

-- Opción A: B-tree clásico.
CREATE INDEX idx_cotizacion_fecha_btree ON cotizacion (fecha_cotizacion);
ANALYZE cotizacion;

\echo '\n=========== O3 · DESPUÉS con B-tree ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT q.modalidad, count(*) AS cotizaciones, count(o.id_operacion) AS operaciones
FROM cotizacion q
LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
GROUP BY q.modalidad;

-- Opción B: BRIN. Guarda solo el mínimo y el máximo de cada bloque de 128 páginas;
-- funciona porque las fechas crecen junto con la posición física de las filas.
CREATE INDEX idx_cotizacion_fecha_brin ON cotizacion USING brin (fecha_cotizacion);

\echo '\n=========== O3 · Tamaño: B-tree vs. BRIN ==========='
SELECT indexrelname AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tamano
FROM pg_stat_user_indexes
WHERE indexrelname IN ('idx_cotizacion_fecha_btree', 'idx_cotizacion_fecha_brin');

DROP INDEX idx_cotizacion_fecha_btree;
ANALYZE cotizacion;

\echo '\n=========== O3 · DESPUÉS con BRIN ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT q.modalidad, count(*) AS cotizaciones, count(o.id_operacion) AS operaciones
FROM cotizacion q
LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
GROUP BY q.modalidad;


-- -----------------------------------------------------------------------------
-- O3 · Paso 2: el índice solo no basta
-- El plan con BRIN muestra que el acceso a cotizacion ya es barato (~26 ms), pero el
-- cuello de botella sigue siendo el Parallel Seq Scan de las 918 mil operaciones que
-- alimenta el Hash Join. Regla de negocio: una operación solo puede crearse durante
-- la vigencia de la cotización (5 min) más la gracia (10 min). Entonces se puede
-- acotar también operacion por fecha_operacion sin cambiar el resultado, y esa
-- columna (también insertada en orden cronológico) admite un BRIN.
-- -----------------------------------------------------------------------------
CREATE INDEX idx_operacion_fecha_brin ON operacion USING brin (fecha_operacion);
ANALYZE operacion;

\echo '\n=========== O3 · DESPUÉS con BRIN + reescritura (rango también en operacion) ==========='
EXPLAIN (ANALYZE, BUFFERS)
SELECT q.modalidad, count(*) AS cotizaciones, count(o.id_operacion) AS operaciones
FROM cotizacion q
LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
      AND o.fecha_operacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
      AND o.fecha_operacion <  TIMESTAMPTZ '2026-10-01 00:00-05' + INTERVAL '15 minutes'
WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
GROUP BY q.modalidad;

\echo '\n=========== O3 · Verificación: ambas versiones devuelven lo mismo (0 filas = idénticas) ==========='
(SELECT q.modalidad, count(*), count(o.id_operacion)
 FROM cotizacion q LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
 WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05' AND q.fecha_cotizacion < TIMESTAMPTZ '2026-10-01 00:00-05'
 GROUP BY q.modalidad)
EXCEPT
(SELECT q.modalidad, count(*), count(o.id_operacion)
 FROM cotizacion q LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
      AND o.fecha_operacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
      AND o.fecha_operacion <  TIMESTAMPTZ '2026-10-01 00:00-05' + INTERVAL '15 minutes'
 WHERE q.fecha_cotizacion >= TIMESTAMPTZ '2026-09-01 00:00-05' AND q.fecha_cotizacion < TIMESTAMPTZ '2026-10-01 00:00-05'
 GROUP BY q.modalidad);

\echo '\n=========== O3 · Supuesto de la reescritura: demora máxima cotización → operación ==========='
SELECT max(o.fecha_operacion - q.fecha_cotizacion) AS demora_maxima
FROM operacion o JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion;


-- #############################################################################
-- Índices finales creados por este script
-- #############################################################################
\echo '\n=========== Índices finales ==========='
SELECT relname AS tabla, indexrelname AS indice, pg_size_pretty(pg_relation_size(indexrelid)) AS tamano
FROM pg_stat_user_indexes
WHERE indexrelname IN ('idx_operacion_cliente_fecha', 'idx_operacion_cola_backoffice',
                       'idx_cotizacion_fecha_brin', 'idx_operacion_fecha_brin')
ORDER BY 1, 2;
