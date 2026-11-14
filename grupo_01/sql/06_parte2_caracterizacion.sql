-- =============================================================================
-- NexoCambio · 06_parte2_caracterizacion.sql
-- Parte 2: mide las cifras de la caracterización del problema (informe_final.pdf,
-- sección 2): volumen, frecuencia de eventos, crecimiento, estado "caliente" y costo
-- de calcular las features en PostgreSQL. Requiere 04_queries.sql (vistas) y el
-- índice de O1 (05_indexes.sql). Los tiempos de la sección 5 varían entre corridas:
-- ejecutar el script 5 veces y tomar la mediana.
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/06_parte2_caracterizacion.sql
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path TO nexocambio;
SET TIME ZONE 'America/Lima';

CREATE INDEX IF NOT EXISTS idx_operacion_cliente_fecha ON operacion (id_cliente, fecha_operacion DESC);


\echo '\n=========== 1 · Volumen: filas y tamaño de la base ==========='
SELECT relname AS tabla, n_live_tup AS filas
FROM pg_stat_user_tables WHERE schemaname = 'nexocambio'
ORDER BY n_live_tup DESC;

SELECT sum(n_live_tup) AS filas_totales,
       pg_size_pretty(pg_database_size(current_database())) AS tamano_base
FROM pg_stat_user_tables WHERE schemaname = 'nexocambio';


\echo '\n=========== 2 · Frecuencia: eventos de negocio en septiembre de 2026 ==========='
-- Un evento es una cotización, una operación, un comprobante o un cambio de estado. El
-- estado inicial (estado_anterior NULL) no se cuenta: nace con la operación, en el mismo evento.
CREATE TEMP VIEW eventos_sep AS
SELECT fecha_cotizacion AS f, 'cotizacion' AS tipo FROM cotizacion
 WHERE fecha_cotizacion >= '2026-09-01' AND fecha_cotizacion < '2026-10-01'
UNION ALL
SELECT fecha_operacion, 'operacion' FROM operacion
 WHERE fecha_operacion >= '2026-09-01' AND fecha_operacion < '2026-10-01'
UNION ALL
SELECT fecha_subida, 'comprobante' FROM comprobante
 WHERE fecha_subida >= '2026-09-01' AND fecha_subida < '2026-10-01'
UNION ALL
SELECT fecha_cambio, 'cambio_estado' FROM historial_estado
 WHERE fecha_cambio >= '2026-09-01' AND fecha_cambio < '2026-10-01' AND estado_anterior IS NOT NULL;

SELECT tipo, count(*) AS eventos, round(count(*) / 30.0) AS por_dia
FROM eventos_sep GROUP BY ROLLUP (tipo) ORDER BY eventos;

SELECT max(n) AS pico_por_hora FROM (SELECT count(*) AS n FROM eventos_sep GROUP BY date_trunc('hour', f)) h;
SELECT max(n) AS pico_por_minuto FROM (SELECT count(*) AS n FROM eventos_sep GROUP BY date_trunc('minute', f)) m;


\echo '\n=========== 3 · Crecimiento: operaciones por día ==========='
SELECT to_char(date_trunc('month', fecha_operacion), 'YYYY-MM') AS mes,
       count(*) AS operaciones,
       round(count(*) / extract(day FROM date_trunc('month', min(fecha_operacion)) + INTERVAL '1 month - 1 day')) AS por_dia
FROM operacion
WHERE fecha_operacion < '2026-10-01'
GROUP BY 1 HAVING to_char(date_trunc('month', fecha_operacion), 'YYYY-MM') IN ('2025-01', '2026-09')
ORDER BY 1;


\echo '\n=========== 4 · Estado "caliente" para el scoring (corte 22/10/2026) ==========='
SELECT count(DISTINCT id_cliente) AS clientes_activos_90d
FROM operacion WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days';

SELECT round(avg(n), 1) AS operaciones_120d_por_cliente_activo
FROM (SELECT id_cliente, count(*) AS n FROM operacion
      WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '120 days'
        AND id_cliente IN (SELECT id_cliente FROM operacion
                           WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days')
      GROUP BY id_cliente) x;


\echo '\n=========== 5 · Costo de las features en PostgreSQL (v_features_cliente) ==========='
SELECT id_cliente AS cli_tipico FROM cliente WHERE codigo_cliente = 'CLI-06EZN7' \gset
SELECT id_cliente AS cli_pitufeo FROM cliente WHERE codigo_cliente = 'CLI-ZYCHEZ' \gset

SELECT codigo_cliente, count(*) AS operaciones
FROM operacion JOIN cliente USING (id_cliente)
WHERE id_cliente IN (:cli_tipico, :cli_pitufeo) GROUP BY codigo_cliente;

\echo '\n-- Cliente típico (CLI-06EZN7)'
EXPLAIN (ANALYZE, SUMMARY ON, TIMING OFF, COSTS OFF) SELECT * FROM v_features_cliente WHERE id_cliente = :cli_tipico;
\echo '\n-- Cliente con fraccionamiento (CLI-ZYCHEZ)'
EXPLAIN (ANALYZE, SUMMARY ON, TIMING OFF, COSTS OFF) SELECT * FROM v_features_cliente WHERE id_cliente = :cli_pitufeo;
\echo '\n-- Todos los clientes (batch)'
EXPLAIN (ANALYZE, SUMMARY ON, TIMING OFF, COSTS OFF) SELECT count(*) FROM v_features_cliente;
