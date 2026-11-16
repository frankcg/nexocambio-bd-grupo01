-- =============================================================================
-- NexoCambio · 08_oportunidades_ingreso.sql
-- Parte 2: mide las dos oportunidades de ingreso que usan la misma arquitectura que el caso de
-- cumplimiento (informe_final.pdf, sección 5.2):
--   A. Cotizaciones abandonadas: el cliente registrado cotizó y no operó en las 24 h siguientes.
--   B. Clientes frecuentes que se están enfriando (reactivación; es la lógica de C9).
-- Ventana: los 90 días anteriores al corte (22/10/2026).
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/08_oportunidades_ingreso.sql
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path TO nexocambio;
SET TIME ZONE 'America/Lima';

\echo '\n=========== Referencia · ingreso por spread cobrado (operaciones procesadas) ==========='
SELECT round(sum(monto_usd * spread_aplicado)) AS spread_90d_usd,
       round(sum(monto_usd * spread_aplicado) FILTER (WHERE fecha_operacion >= TIMESTAMPTZ '2026-09-01 00:00-05'
                                                       AND fecha_operacion <  TIMESTAMPTZ '2026-10-01 00:00-05'))
           AS spread_septiembre_usd
FROM v_operacion
WHERE estado_actual = 'Procesada'
  AND fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
  AND fecha_operacion <  TIMESTAMPTZ '2026-10-22 00:00-05';


\echo '\n=========== A · Cotizaciones no convertidas de clientes registrados: ¿operó después? ==========='
-- Se excluye el último día para dejar 24 h de observación.
CREATE TEMP TABLE cot_no_convertida AS
SELECT q.id_cotizacion, q.id_cliente, q.fecha_cotizacion, q.spread_aplicado,
       round(q.monto_origen * coalesce(t.precio_usd, 1), 2) AS monto_usd,
       (SELECT min(o.fecha_operacion) FROM operacion o
        WHERE o.id_cliente = q.id_cliente AND o.fecha_operacion > q.fecha_cotizacion
          AND o.fecha_operacion <= q.fecha_cotizacion + INTERVAL '24 hours') AS opero_despues
FROM cotizacion q
LEFT JOIN tasa_referencial t ON t.codigo_moneda = q.moneda_origen
     AND t.fecha_hora = date_bin('5 minutes', q.fecha_cotizacion, TIMESTAMPTZ '2025-01-01 00:00-05')
WHERE q.id_cliente IS NOT NULL
  AND q.fecha_cotizacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
  AND q.fecha_cotizacion <  TIMESTAMPTZ '2026-10-21 00:00-05'
  AND NOT EXISTS (SELECT 1 FROM operacion o WHERE o.id_cotizacion = q.id_cotizacion);

SELECT CASE WHEN opero_despues IS NULL THEN '3. No operó en 24 h (intención perdida)'
            WHEN opero_despues <= fecha_cotizacion + INTERVAL '30 minutes' THEN '1. Operó en ≤ 30 min (volvió a cotizar)'
            ELSE '2. Operó entre 30 min y 24 h' END AS resultado,
       count(*) AS cotizaciones, count(DISTINCT id_cliente) AS clientes,
       round(sum(monto_usd)) AS volumen_usd, round(sum(monto_usd * spread_aplicado)) AS spread_usd
FROM cot_no_convertida GROUP BY 1 ORDER BY 1;

\echo '\n== A · Intención perdida sin duplicados: un caso por cliente y día (la cotización de mayor monto) =='
SELECT count(*) AS casos_cliente_dia, round(count(*) / 89.0) AS casos_por_dia,
       count(DISTINCT id_cliente) AS clientes, round(avg(monto_usd)) AS ticket_prom_usd,
       round(sum(monto_usd)) AS volumen_usd, round(sum(monto_usd * spread_aplicado)) AS spread_no_cobrado_usd,
       count(*) FILTER (WHERE monto_usd >= 5000) AS casos_desde_5000_usd
FROM (SELECT DISTINCT ON (id_cliente, fecha_cotizacion::date) *
      FROM cot_no_convertida WHERE opero_despues IS NULL
      ORDER BY id_cliente, fecha_cotizacion::date, monto_usd DESC) casos;


\echo '\n=========== B · Clientes frecuentes (≥ 5 operaciones) según su inactividad ==========='
-- Activo: inactivo ≤ 2 × su intervalo habitual. En riesgo: más que eso, pero ≤ 120 días.
-- Abandono: más de 120 días. El ingreso es el spread mensual promedio mientras estuvo activo.
WITH ops AS (
    SELECT id_cliente, fecha_operacion, monto_usd, spread_aplicado,
           LAG(fecha_operacion) OVER (PARTITION BY id_cliente ORDER BY fecha_operacion) AS anterior
    FROM v_operacion WHERE estado_actual = 'Procesada' AND fecha_operacion < TIMESTAMPTZ '2026-10-22 00:00-05'
), cli AS (
    SELECT id_cliente,
           avg(extract(epoch FROM fecha_operacion - anterior) / 86400) AS intervalo,
           extract(epoch FROM TIMESTAMPTZ '2026-10-22 00:00-05' - max(fecha_operacion)) / 86400 AS inactivo,
           sum(monto_usd * spread_aplicado)
             / greatest(extract(epoch FROM max(fecha_operacion) - min(fecha_operacion)) / 86400 / 30.4, 1) AS spread_mes
    FROM ops GROUP BY 1 HAVING count(*) >= 5
)
SELECT CASE WHEN inactivo <= 2 * intervalo THEN '1. Activo' WHEN inactivo <= 120 THEN '2. En riesgo'
            ELSE '3. Abandono' END AS segmento,
       count(*) AS clientes, round(avg(inactivo)) AS dias_inactivo_prom,
       round(sum(spread_mes)) AS spread_mensual_cuando_activos_usd
FROM cli GROUP BY 1 ORDER BY 1;
