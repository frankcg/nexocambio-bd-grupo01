-- =============================================================================
-- NexoCambio · 04_queries.sql
-- Parte A: 10 consultas orientadas al negocio (básicas, intermedias y avanzadas).
-- Parte B: 8 features para un modelo de detección de operaciones inusuales.
--
-- Fecha de corte del análisis: 22/10/2026 00:00 (Lima), el día siguiente al último dato.
-- Se usa una fecha fija en lugar de now() para que los resultados sean reproducibles.
--   cd grupo_01
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/04_queries.sql
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path TO nexocambio;

-- -----------------------------------------------------------------------------
-- Vista de apoyo: operación + cotización + monto equivalente en USD.
-- El monto en USD usa la tasa de referencia del bloque de 5 minutos de la cotización
-- (búsqueda por igualdad sobre el índice único uq_tasa_moneda_fecha). El USD no tiene
-- filas en tasa_referencial: su precio es 1.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_operacion AS
SELECT o.id_operacion, o.codigo_operacion, o.id_cliente, c.tipo_cliente, o.estado_actual,
       o.fecha_operacion, o.fecha_actualizacion, o.motivo_rechazo,
       o.id_cuenta_origen, o.id_cuenta_destino,
       q.id_cotizacion, q.modalidad, q.moneda_origen, q.moneda_destino,
       q.monto_origen, q.monto_destino, q.tasa, q.spread_aplicado, q.tasa_preferencial,
       round(q.monto_origen * coalesce(t.precio_usd, 1), 2) AS monto_usd
FROM operacion o
JOIN cotizacion q  ON q.id_cotizacion = o.id_cotizacion
JOIN cliente c     ON c.id_cliente = o.id_cliente
LEFT JOIN tasa_referencial t
       ON t.codigo_moneda = q.moneda_origen
      AND t.fecha_hora = date_bin('5 minutes', q.fecha_cotizacion, TIMESTAMPTZ '2025-01-01 00:00-05');

COMMENT ON VIEW v_operacion IS 'Operación con los datos de su cotización y su monto equivalente en USD.';


-- #############################################################################
-- PARTE A · CONSULTAS DE NEGOCIO
-- #############################################################################

-- =============================================================================
-- C1 · [Básica] ¿Qué pares de monedas concentran el volumen procesado en 2026?
-- Conceptos: WHERE, INNER JOIN (vista), GROUP BY, HAVING, agregaciones, ORDER BY.
-- =============================================================================
\echo '\n== C1 · Volumen procesado por par de monedas (2026) =='
SELECT modalidad,
       moneda_origen || '/' || moneda_destino AS par,
       count(*)                                 AS operaciones,
       round(sum(monto_usd))                    AS volumen_usd,
       round(avg(monto_usd), 2)                 AS ticket_promedio_usd,
       round(100.0 * count(*) FILTER (WHERE tasa_preferencial) / count(*), 1) AS pct_preferencial
FROM v_operacion
WHERE estado_actual = 'Procesada'
  AND fecha_operacion >= TIMESTAMPTZ '2026-01-01 00:00-05'
GROUP BY modalidad, par
HAVING sum(monto_usd) > 1000000          -- solo pares con más de US$ 1 millón
ORDER BY volumen_usd DESC;


-- =============================================================================
-- C2 · [Intermedia] ¿La tasa de rechazo varía según el banco de origen? ¿Cuál es el motivo más común?
-- Conceptos: INNER JOIN (3 tablas), agregación condicional (FILTER), mode(), HAVING.
-- =============================================================================
\echo '\n== C2 · Rechazos por banco de origen =='
SELECT b.nombre                                                        AS banco_origen,
       count(*) FILTER (WHERE o.estado_actual IN ('Procesada', 'Rechazada')) AS decididas,
       count(*) FILTER (WHERE o.estado_actual = 'Rechazada')             AS rechazadas,
       round(100.0 * count(*) FILTER (WHERE o.estado_actual = 'Rechazada')
             / NULLIF(count(*) FILTER (WHERE o.estado_actual IN ('Procesada', 'Rechazada')), 0), 2) AS pct_rechazo,
       mode() WITHIN GROUP (ORDER BY o.motivo_rechazo)                   AS motivo_mas_frecuente
FROM operacion o
JOIN cuenta_cliente cc ON cc.id_cuenta = o.id_cuenta_origen
JOIN banco b           ON b.id_banco = cc.id_banco
GROUP BY b.nombre
HAVING count(*) >= 1000
ORDER BY pct_rechazo DESC;


-- =============================================================================
-- C3 · [Intermedia] ¿Cuántos clientes se registran y nunca operan? (activación por cohorte)
-- Conceptos: LEFT JOIN + IS NULL (anti-join), GROUP BY, agregación condicional.
-- =============================================================================
\echo '\n== C3 · Clientes registrados sin operaciones, por cohorte trimestral =='
SELECT to_char(date_trunc('quarter', c.fecha_registro), 'YYYY-"T"Q') AS cohorte,
       c.tipo_cliente,
       count(*)                                          AS registrados,
       count(*) FILTER (WHERE a.id_cliente IS NULL)      AS sin_operaciones,
       round(100.0 * count(*) FILTER (WHERE a.id_cliente IS NULL) / count(*), 1) AS pct_sin_operar
FROM cliente c
LEFT JOIN (SELECT DISTINCT id_cliente FROM operacion) a ON a.id_cliente = c.id_cliente
GROUP BY date_trunc('quarter', c.fecha_registro), c.tipo_cliente
ORDER BY date_trunc('quarter', c.fecha_registro), c.tipo_cliente;


-- =============================================================================
-- C4 · [Intermedia] ¿Cuánto tarda cada analista de back-office en validar un comprobante?
-- Conceptos: auto-JOIN de historial_estado, INNER JOIN, percentiles, ORDER BY.
-- Mide desde "Pendiente de validación" hasta la decisión (En proceso o Rechazada).
-- =============================================================================
\echo '\n== C4 · Tiempo de validación por analista =='
SELECT u.nombre,
       u.rol,
       count(*)                                                   AS decisiones,
       round(100.0 * count(*) FILTER (WHERE d.estado_nuevo = 'Rechazada') / count(*), 1) AS pct_rechazo,
       round((avg(extract(epoch FROM d.fecha_cambio - p.fecha_cambio)) / 60)::numeric, 1) AS minutos_promedio,
       round((percentile_cont(0.5) WITHIN GROUP
             (ORDER BY extract(epoch FROM d.fecha_cambio - p.fecha_cambio)) / 60)::numeric, 1) AS minutos_mediana
FROM historial_estado d
JOIN historial_estado p   ON p.id_operacion = d.id_operacion
                         AND p.estado_nuevo = 'Pendiente de validación'
JOIN usuario_backoffice u ON u.id_usuario = d.id_usuario
WHERE d.estado_anterior = 'Pendiente de validación'
GROUP BY u.id_usuario, u.nombre, u.rol
ORDER BY minutos_mediana;


-- =============================================================================
-- C5 · [Avanzada] ¿Cómo crece el volumen mes a mes?
-- Conceptos: CTE, LAG, acumulado (SUM OVER con PARTITION), media móvil (ROWS BETWEEN).
-- =============================================================================
\echo '\n== C5 · Crecimiento mensual del volumen procesado =='
WITH mensual AS (
    SELECT date_trunc('month', fecha_operacion) AS mes,
           count(*)                              AS operaciones,
           sum(monto_usd)                        AS volumen_usd
    FROM v_operacion
    WHERE estado_actual = 'Procesada'
    GROUP BY 1
)
SELECT to_char(mes, 'YYYY-MM')                                                       AS mes,
       operaciones,
       round(volumen_usd)                                                            AS volumen_usd,
       round(100 * (volumen_usd / LAG(volumen_usd) OVER (ORDER BY mes) - 1), 1)      AS var_pct_vs_mes_anterior,
       round(sum(volumen_usd) OVER (PARTITION BY date_trunc('year', mes) ORDER BY mes)) AS acumulado_del_anio,
       round(avg(volumen_usd) OVER (ORDER BY mes ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)) AS media_movil_3m
FROM mensual
ORDER BY mes;


-- =============================================================================
-- C6 · [Avanzada] ¿Quiénes son los 3 clientes de mayor volumen cada mes y qué peso tienen?
-- Conceptos: CTE encadenadas, DENSE_RANK, participación con SUM OVER (PARTITION BY).
-- =============================================================================
\echo '\n== C6 · Top 3 clientes por volumen en cada mes (abr–set 2026) =='
WITH por_cliente AS (
    SELECT date_trunc('month', fecha_operacion) AS mes, id_cliente,
           count(*) AS operaciones, sum(monto_usd) AS volumen_usd
    FROM v_operacion
    WHERE estado_actual = 'Procesada'
      AND fecha_operacion >= TIMESTAMPTZ '2026-04-01 00:00-05'
      AND fecha_operacion <  TIMESTAMPTZ '2026-10-01 00:00-05'
    GROUP BY 1, 2
), ranking AS (
    SELECT *,
           DENSE_RANK() OVER (PARTITION BY mes ORDER BY volumen_usd DESC) AS puesto,
           100 * volumen_usd / sum(volumen_usd) OVER (PARTITION BY mes)    AS pct_del_mes
    FROM por_cliente
)
SELECT to_char(r.mes, 'YYYY-MM') AS mes, r.puesto, c.codigo_cliente, c.tipo_cliente,
       r.operaciones, round(r.volumen_usd) AS volumen_usd, round(r.pct_del_mes, 2) AS pct_del_mes
FROM ranking r
JOIN cliente c ON c.id_cliente = r.id_cliente
WHERE r.puesto <= 3
ORDER BY r.mes, r.puesto;


-- =============================================================================
-- C7 · [Avanzada] ¿Dónde se pierde el cliente en el embudo cotización → operación → procesada?
-- Conceptos: CTE, CASE, LEFT JOIN, agregación condicional, ROLLUP (subtotales).
-- =============================================================================
\echo '\n== C7 · Embudo de conversión por modalidad y canal =='
WITH base AS (
    SELECT q.modalidad,
           CASE WHEN q.id_cliente IS NULL THEN 'Visitante' ELSE 'Con sesión' END AS canal,
           o.id_operacion,
           o.estado_actual
    FROM cotizacion q
    LEFT JOIN operacion o ON o.id_cotizacion = q.id_cotizacion
)
SELECT coalesce(modalidad, 'TOTAL')  AS modalidad,
       coalesce(canal, '(todos)')    AS canal,
       count(*)                      AS cotizaciones,
       count(id_operacion)           AS operaciones,
       round(100.0 * count(id_operacion) / count(*), 1)                                        AS pct_conversion,
       round(100.0 * count(*) FILTER (WHERE estado_actual = 'Pendiente de comprobante')
             / NULLIF(count(id_operacion), 0), 1)                                              AS pct_sin_comprobante,
       round(100.0 * count(*) FILTER (WHERE estado_actual = 'Procesada')
             / NULLIF(count(id_operacion), 0), 1)                                              AS pct_procesadas
FROM base
GROUP BY ROLLUP (modalidad, canal)
ORDER BY modalidad NULLS LAST, canal NULLS LAST;


-- =============================================================================
-- C8 · [Avanzada] ¿Cuánto ingreso por spread genera cada segmento por trimestre?
-- Conceptos: agregación + función ventana sobre el agregado (participación), CASE implícito.
-- Ingreso aproximado = monto_usd × spread_aplicado (diferencia contra la tasa de mercado).
-- =============================================================================
\echo '\n== C8 · Ingreso por spread por trimestre, tipo de cliente y modalidad =='
SELECT to_char(date_trunc('quarter', fecha_operacion), 'YYYY-"T"Q')   AS trimestre,
       tipo_cliente,
       modalidad,
       round(sum(monto_usd * spread_aplicado), 2)                       AS ingreso_spread_usd,
       round(100 * sum(monto_usd * spread_aplicado)
             / sum(sum(monto_usd * spread_aplicado)) OVER (PARTITION BY date_trunc('quarter', fecha_operacion)), 1)
                                                                        AS pct_del_trimestre,
       round(10000 * sum(monto_usd * spread_aplicado) / sum(monto_usd), 1) AS margen_pb
FROM v_operacion
WHERE estado_actual = 'Procesada'
GROUP BY date_trunc('quarter', fecha_operacion), tipo_cliente, modalidad
ORDER BY date_trunc('quarter', fecha_operacion), ingreso_spread_usd DESC;


-- =============================================================================
-- C9 · [Avanzada] ¿Qué clientes frecuentes están dejando de operar?
-- Conceptos: LAG (intervalo entre operaciones), CTE, CASE, comparación contra el ritmo
-- propio del cliente (días inactivo vs. su intervalo promedio), análisis temporal.
-- =============================================================================
\echo '\n== C9 · Segmentación de abandono de clientes frecuentes =='
WITH ops AS (
    SELECT id_cliente, fecha_operacion,
           LAG(fecha_operacion) OVER (PARTITION BY id_cliente ORDER BY fecha_operacion) AS anterior
    FROM operacion
    WHERE estado_actual = 'Procesada'
), perfil AS (
    SELECT id_cliente,
           count(*)                                                        AS operaciones,
           avg(extract(epoch FROM fecha_operacion - anterior)) / 86400     AS intervalo_prom_dias,
           extract(epoch FROM TIMESTAMPTZ '2026-10-22 00:00-05' - max(fecha_operacion)) / 86400 AS dias_inactivo
    FROM ops
    GROUP BY id_cliente
    HAVING count(*) >= 5                     -- clientes frecuentes
)
SELECT CASE WHEN dias_inactivo <= 2 * intervalo_prom_dias THEN '1. Activo'
            WHEN dias_inactivo <= 4 * intervalo_prom_dias THEN '2. En riesgo'
            ELSE '3. Abandono' END                    AS segmento,
       count(*)                                       AS clientes,
       round(avg(operaciones))                        AS operaciones_prom,
       round(avg(intervalo_prom_dias)::numeric, 1)    AS intervalo_prom_dias,
       round(avg(dias_inactivo)::numeric, 1)          AS dias_inactivo_prom
FROM perfil
GROUP BY 1
ORDER BY 1;


-- =============================================================================
-- C10 · [Avanzada] ¿Qué operaciones se alejan del comportamiento habitual del cliente?
-- Conceptos: AVG y COUNT como funciones ventana (PARTITION BY), comparación contra el
-- promedio propio, ROW_NUMBER para quedarse con la más extrema de cada cliente.
-- =============================================================================
\echo '\n== C10 · Operaciones de más de 5 veces el promedio del cliente =='
WITH historial AS (
    SELECT id_operacion, codigo_operacion, id_cliente, fecha_operacion, monto_usd, estado_actual,
           avg(monto_usd) OVER (PARTITION BY id_cliente) AS promedio_cliente,
           count(*)       OVER (PARTITION BY id_cliente) AS ops_cliente
    FROM v_operacion
    WHERE estado_actual <> 'Pendiente de comprobante'
), atipicas AS (
    SELECT *, monto_usd / promedio_cliente AS veces_promedio,
           ROW_NUMBER() OVER (PARTITION BY id_cliente ORDER BY monto_usd / promedio_cliente DESC) AS rn
    FROM historial
    WHERE ops_cliente >= 10
      AND monto_usd >= 10000
      AND monto_usd > 5 * promedio_cliente
)
SELECT c.codigo_cliente, a.codigo_operacion, a.fecha_operacion::date AS fecha, a.estado_actual,
       round(a.monto_usd) AS monto_usd, round(a.promedio_cliente) AS promedio_cliente,
       round(a.veces_promedio, 1) AS veces_promedio
FROM atipicas a
JOIN cliente c ON c.id_cliente = a.id_cliente
WHERE a.rn = 1
ORDER BY a.veces_promedio DESC
LIMIT 15;


-- #############################################################################
-- PARTE B · FEATURE ENGINEERING (por cliente, a la fecha de corte)
-- Objetivo: alimentar un modelo de detección de operaciones inusuales (Parte 2).
-- #############################################################################

-- F1 · operaciones_30d: operaciones creadas en los últimos 30 días.
\echo '\n== F1 · operaciones_30d (top 5) =='
SELECT id_cliente, count(*) AS operaciones_30d
FROM operacion
WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days'
GROUP BY id_cliente
ORDER BY operaciones_30d DESC
LIMIT 5;

-- F2 · monto_promedio_usd_90d: ticket promedio en USD de los últimos 90 días.
\echo '\n== F2 · monto_promedio_usd_90d (top 5) =='
SELECT id_cliente, round(avg(monto_usd), 2) AS monto_promedio_usd_90d
FROM v_operacion
WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
GROUP BY id_cliente
ORDER BY monto_promedio_usd_90d DESC
LIMIT 5;

-- F3 · dias_desde_ultima_operacion: recencia (días entre la última operación y el corte).
\echo '\n== F3 · dias_desde_ultima_operacion (distribución) =='
SELECT width_bucket(dias, 0, 600, 6) AS tramo, min(dias) AS desde, max(dias) AS hasta, count(*) AS clientes
FROM (SELECT id_cliente,
             round(extract(epoch FROM TIMESTAMPTZ '2026-10-22 00:00-05' - max(fecha_operacion)) / 86400) AS dias
      FROM operacion GROUP BY id_cliente) r
GROUP BY 1 ORDER BY 1;

-- F4 · ratio_rechazo: rechazadas / decididas en toda la historia del cliente.
\echo '\n== F4 · ratio_rechazo (clientes con 10+ decisiones, top 5) =='
SELECT id_cliente,
       count(*) FILTER (WHERE estado_actual IN ('Procesada', 'Rechazada')) AS decididas,
       round(count(*) FILTER (WHERE estado_actual = 'Rechazada')::numeric
             / NULLIF(count(*) FILTER (WHERE estado_actual IN ('Procesada', 'Rechazada')), 0), 3) AS ratio_rechazo
FROM operacion
GROUP BY id_cliente
HAVING count(*) FILTER (WHERE estado_actual IN ('Procesada', 'Rechazada')) >= 10
ORDER BY ratio_rechazo DESC
LIMIT 5;

-- F5 · ratio_cerca_umbral_90d: proporción de operaciones entre US$ 9 000 y US$ 9 999,99.
-- La UIF exige registrar las operaciones desde US$ 10 000; fraccionar justo por debajo
-- ("pitufeo") es una señal clásica de lavado de activos.
\echo '\n== F5 · ratio_cerca_umbral_90d (top 5) =='
SELECT id_cliente, count(*) AS operaciones_90d,
       round(avg(CASE WHEN monto_usd >= 9000 AND monto_usd < 10000 THEN 1 ELSE 0 END), 3) AS ratio_cerca_umbral_90d
FROM v_operacion
WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '90 days'
GROUP BY id_cliente
HAVING count(*) >= 3
ORDER BY ratio_cerca_umbral_90d DESC, operaciones_90d DESC
LIMIT 5;

-- F6 · ratio_cuentas_terceros: proporción de operaciones cuyo destino es una cuenta
-- bancaria cuyo titular no es el propio cliente.
\echo '\n== F6 · ratio_cuentas_terceros (top 5) =='
WITH nombre_cliente AS (
    SELECT id_cliente, nombres || ' ' || apellidos AS nombre FROM persona_natural
    UNION ALL
    SELECT id_cliente, razon_social FROM empresa
)
SELECT o.id_cliente,
       count(*)                        AS operaciones_a_banco,
       count(DISTINCT o.id_cuenta_destino) AS cuentas_destino,
       round(avg(CASE WHEN cc.titular <> n.nombre THEN 1 ELSE 0 END), 3) AS ratio_cuentas_terceros
FROM operacion o
JOIN cuenta_cliente cc ON cc.id_cuenta = o.id_cuenta_destino AND cc.tipo = 'banco'
JOIN nombre_cliente n  ON n.id_cliente = o.id_cliente
GROUP BY o.id_cliente
HAVING count(*) >= 5
ORDER BY ratio_cuentas_terceros DESC, cuentas_destino DESC
LIMIT 5;

-- F7 · variacion_monto_30d: ticket promedio de los últimos 30 días dividido entre el de
-- los 90 días anteriores (31 a 120 días). > 1 = el cliente está operando montos mayores.
\echo '\n== F7 · variacion_monto_30d (top 5) =='
SELECT id_cliente,
       round(avg(monto_usd) FILTER (WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days'), 2) AS ticket_30d,
       round(avg(monto_usd) FILTER (WHERE fecha_operacion <  TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days'), 2) AS ticket_previo,
       round(avg(monto_usd) FILTER (WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days')
             / avg(monto_usd) FILTER (WHERE fecha_operacion <  TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days'), 2)
                                                                                                                     AS variacion_monto_30d
FROM v_operacion
WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '120 days'
GROUP BY id_cliente
HAVING count(*) FILTER (WHERE fecha_operacion >= TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days') >= 1
   AND count(*) FILTER (WHERE fecha_operacion <  TIMESTAMPTZ '2026-10-22 00:00-05' - INTERVAL '30 days') >= 3
ORDER BY variacion_monto_30d DESC
LIMIT 5;

-- F8 · ratio_nocturno: proporción de operaciones entre las 00:00 y las 04:59 (hora de Lima).
\echo '\n== F8 · ratio_nocturno (top 5) =='
SELECT id_cliente, count(*) AS operaciones,
       round(avg(CASE WHEN extract(hour FROM fecha_operacion) < 5 THEN 1 ELSE 0 END), 3) AS ratio_nocturno
FROM operacion
GROUP BY id_cliente
HAVING count(*) >= 5
ORDER BY ratio_nocturno DESC
LIMIT 5;


-- =============================================================================
-- Vector de features consolidado (una fila por cliente con operaciones).
-- Es la tabla que se exportaría al pipeline de ML (Parte 2).
-- =============================================================================
CREATE OR REPLACE VIEW v_features_cliente AS
WITH corte AS (SELECT TIMESTAMPTZ '2026-10-22 00:00-05' AS f),
nombre_cliente AS (
    SELECT id_cliente, nombres || ' ' || apellidos AS nombre, es_pep FROM persona_natural
    UNION ALL
    SELECT id_cliente, razon_social, false FROM empresa
),
ops AS (
    SELECT v.*, cc.titular AS titular_destino, cc.tipo AS tipo_destino
    FROM v_operacion v
    JOIN cuenta_cliente cc ON cc.id_cuenta = v.id_cuenta_destino
)
SELECT o.id_cliente,
       c.tipo_cliente,
       n.es_pep,
       round(extract(epoch FROM (SELECT f FROM corte) - c.fecha_registro) / 86400)              AS antiguedad_dias,
       count(*) FILTER (WHERE o.fecha_operacion >= (SELECT f FROM corte) - INTERVAL '30 days')   AS operaciones_30d,
       round(avg(o.monto_usd) FILTER (WHERE o.fecha_operacion >= (SELECT f FROM corte) - INTERVAL '90 days'), 2)
                                                                                                AS monto_promedio_usd_90d,
       round(extract(epoch FROM (SELECT f FROM corte) - max(o.fecha_operacion)) / 86400)        AS dias_desde_ultima_operacion,
       round(count(*) FILTER (WHERE o.estado_actual = 'Rechazada')::numeric
             / NULLIF(count(*) FILTER (WHERE o.estado_actual IN ('Procesada', 'Rechazada')), 0), 3) AS ratio_rechazo,
       round(avg(CASE WHEN o.monto_usd >= 9000 AND o.monto_usd < 10000 THEN 1 ELSE 0 END)
             FILTER (WHERE o.fecha_operacion >= (SELECT f FROM corte) - INTERVAL '90 days'), 3)  AS ratio_cerca_umbral_90d,
       round(avg(CASE WHEN o.titular_destino <> n.nombre THEN 1 ELSE 0 END)
             FILTER (WHERE o.tipo_destino = 'banco'), 3)                                        AS ratio_cuentas_terceros,
       round(avg(o.monto_usd) FILTER (WHERE o.fecha_operacion >= (SELECT f FROM corte) - INTERVAL '30 days')
             / NULLIF(avg(o.monto_usd) FILTER (WHERE o.fecha_operacion <  (SELECT f FROM corte) - INTERVAL '30 days'
                                                 AND o.fecha_operacion >= (SELECT f FROM corte) - INTERVAL '120 days'), 0), 2)
                                                                                                AS variacion_monto_30d,
       round(avg(CASE WHEN extract(hour FROM o.fecha_operacion) < 5 THEN 1 ELSE 0 END), 3)      AS ratio_nocturno
FROM ops o
JOIN cliente c        ON c.id_cliente = o.id_cliente
JOIN nombre_cliente n ON n.id_cliente = o.id_cliente
GROUP BY o.id_cliente, c.tipo_cliente, c.fecha_registro, n.es_pep;

COMMENT ON VIEW v_features_cliente IS 'Features por cliente para el modelo de detección de operaciones inusuales.';

\echo '\n== Vector de features: resumen =='
SELECT count(*)                                    AS clientes,
       round(avg(operaciones_30d), 2)              AS operaciones_30d_prom,
       round(avg(monto_promedio_usd_90d), 2)       AS monto_promedio_usd_90d_prom,
       round(avg(dias_desde_ultima_operacion))     AS dias_desde_ultima_prom,
       round(avg(ratio_rechazo), 3)                AS ratio_rechazo_prom,
       round(avg(ratio_cerca_umbral_90d), 3)       AS ratio_cerca_umbral_prom,
       round(avg(ratio_cuentas_terceros), 3)       AS ratio_cuentas_terceros_prom,
       round(avg(ratio_nocturno), 3)               AS ratio_nocturno_prom
FROM v_features_cliente;


-- =============================================================================
-- Validación de las features contra las anomalías inyectadas por el generador.
-- Las etiquetas NO forman parte del modelo de negocio: se cargan en una tabla temporal
-- solo para comprobar que las features separan a los perfiles inusuales de los normales.
-- =============================================================================
CREATE TEMP TABLE etiqueta (codigo_cliente VARCHAR(10) PRIMARY KEY, perfil VARCHAR(12) NOT NULL);
\copy etiqueta FROM 'datos/completo/etiquetas_anomalias.csv' WITH (FORMAT csv, HEADER true)

\echo '\n== Validación: promedio de cada feature por perfil =='
SELECT coalesce(e.perfil, 'normal')               AS perfil,
       count(*)                                   AS clientes,
       round(avg(f.operaciones_30d), 1)           AS operaciones_30d,
       round(avg(f.monto_promedio_usd_90d))       AS monto_prom_usd_90d,
       round(avg(f.ratio_rechazo), 3)             AS ratio_rechazo,
       round(avg(f.ratio_cerca_umbral_90d), 3)    AS ratio_cerca_umbral,
       round(avg(f.ratio_cuentas_terceros), 3)    AS ratio_cuentas_terceros,
       round(avg(f.variacion_monto_30d), 2)       AS variacion_monto_30d,
       round(avg(f.ratio_nocturno), 3)            AS ratio_nocturno
FROM v_features_cliente f
JOIN cliente c        ON c.id_cliente = f.id_cliente
LEFT JOIN etiqueta e  ON e.codigo_cliente = c.codigo_cliente
GROUP BY 1
ORDER BY clientes DESC;
