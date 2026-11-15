-- =============================================================================
-- NexoCambio · Demo, acto 1: PostgreSQL (Parte 1). Pausa entre pasos: Enter para seguir.
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f demo/acto1_postgresql.sql
-- =============================================================================
SET search_path TO nexocambio;
SET TIME ZONE 'America/Lima';
\pset footer off
SELECT id_cliente AS zychez FROM cliente WHERE codigo_cliente = 'CLI-ZYCHEZ' \gset
SELECT id_cliente AS tipico FROM cliente WHERE codigo_cliente = 'CLI-06EZN7' \gset
SELECT id_operacion AS op_procesada FROM operacion
WHERE id_cliente = :zychez AND estado_actual = 'Procesada' ORDER BY fecha_operacion DESC LIMIT 1 \gset
SELECT min(id_usuario) AS analista FROM usuario_backoffice \gset


\echo '\n=== 1 · El modelo protege las reglas del negocio ==='
\echo 'Un analista intenta devolver a "En proceso" una operación ya Procesada:'
\prompt '(Enter) ' _
INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario)
VALUES (:op_procesada, 'Procesada', 'En proceso', :analista);
\echo '→ Rechazado por el CHECK ck_historial_transicion (máquina de estados).'


\echo '\n=== 2 · Insight (C6): los 3 clientes de mayor volumen cada mes ==='
\prompt '(Enter) ' _
WITH por_cliente AS (
    SELECT date_trunc('month', fecha_operacion) AS mes, id_cliente,
           count(*) AS operaciones, sum(monto_usd) AS volumen_usd
    FROM v_operacion
    WHERE estado_actual = 'Procesada'
      AND fecha_operacion >= TIMESTAMPTZ '2026-07-01 00:00-05'
      AND fecha_operacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
    GROUP BY 1, 2
), ranking AS (
    SELECT *, DENSE_RANK() OVER (PARTITION BY mes ORDER BY volumen_usd DESC) AS puesto
    FROM por_cliente
)
SELECT to_char(r.mes, 'YYYY-MM') AS mes, r.puesto, c.codigo_cliente, r.operaciones,
       round(r.volumen_usd) AS volumen_usd, round(r.volumen_usd / r.operaciones) AS ticket_usd
FROM ranking r JOIN cliente c ON c.id_cliente = r.id_cliente
WHERE r.puesto <= 3
ORDER BY r.mes, r.puesto;
\echo '→ CLI-ZYCHEZ es el cliente de mayor volumen todos los meses. ¿Es un buen cliente?'


\echo '\n=== 3 · Las features lo delatan ==='
\prompt '(Enter) ' _
SELECT c.codigo_cliente, f.operaciones_30d, f.monto_promedio_usd_90d AS ticket_90d,
       f.ratio_cerca_umbral_90d, f.ratio_rechazo
FROM v_features_cliente f JOIN cliente c USING (id_cliente)
WHERE f.id_cliente IN (:tipico, :zychez)
ORDER BY f.operaciones_30d;
\echo '→ 75 % de sus operaciones están entre US$ 9 000 y 9 999, justo debajo del umbral de registro'
\echo '  de la UIF (un cliente normal: 0,4 %). Es fraccionamiento ("pitufeo"): el mejor cliente es el más riesgoso.'


\echo '\n=== 4 · Optimización (O1): historial de un cliente en 90 días ==='
\echo 'ANTES, sin índice en operacion.id_cliente (solo el BRIN por fecha de la optimización O3):'
\prompt '(Enter) ' _
DROP INDEX IF EXISTS idx_operacion_cliente_fecha;
EXPLAIN (ANALYZE, COSTS OFF)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual, q.monto_origen
FROM operacion o JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion
WHERE o.id_cliente = :tipico
  AND o.fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
ORDER BY o.fecha_operacion DESC;

\echo '\nCREATE INDEX idx_operacion_cliente_fecha ON operacion (id_cliente, fecha_operacion DESC);'
\prompt '(Enter) ' _
CREATE INDEX idx_operacion_cliente_fecha ON operacion (id_cliente, fecha_operacion DESC);
ANALYZE operacion;

\echo 'DESPUÉS:'
EXPLAIN (ANALYZE, COSTS OFF)
SELECT o.codigo_operacion, o.fecha_operacion, o.estado_actual, q.monto_origen
FROM operacion o JOIN cotizacion q ON q.id_cotizacion = o.id_cotizacion
WHERE o.id_cliente = :tipico
  AND o.fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
ORDER BY o.fecha_operacion DESC;
\echo '→ Antes: leía las operaciones de 90 días de TODOS los clientes (≈ 230 mil) y descartaba casi todas, más un Sort.'
\echo '  Después: el índice va directo a las 26 operaciones del cliente, ya ordenadas (sin Sort).'
