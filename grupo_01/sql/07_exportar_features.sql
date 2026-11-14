-- =============================================================================
-- NexoCambio · 07_exportar_features.sql
-- Parte 2: exporta el vector de features (v_features_cliente) a datos/features_clientes.csv
-- para entrenar el modelo en Databricks (notebooks/modelo_anomalias.py).
--
-- Agrega la columna perfil_anomalia (vacía en los clientes normales), tomada de
-- datos/completo/etiquetas_anomalias.csv. Solo sirve para EVALUAR el modelo, que es no
-- supervisado: nunca se usa para entrenarlo.
--   cd grupo_01
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/07_exportar_features.sql
-- =============================================================================
\set ON_ERROR_STOP on
SET search_path TO nexocambio;

CREATE TEMP TABLE etiqueta (codigo_cliente VARCHAR(10) PRIMARY KEY, perfil VARCHAR(20) NOT NULL);
\copy etiqueta FROM 'datos/completo/etiquetas_anomalias.csv' WITH (FORMAT csv, HEADER true)

\copy (SELECT c.codigo_cliente, f.tipo_cliente, f.es_pep, f.antiguedad_dias, f.operaciones_30d, f.monto_promedio_usd_90d, f.dias_desde_ultima_operacion, f.ratio_rechazo, f.ratio_cerca_umbral_90d, f.ratio_cuentas_terceros, f.variacion_monto_30d, f.ratio_nocturno, e.perfil AS perfil_anomalia FROM v_features_cliente f JOIN cliente c USING (id_cliente) LEFT JOIN etiqueta e USING (codigo_cliente) ORDER BY c.codigo_cliente) TO 'datos/features_clientes.csv' WITH (FORMAT csv, HEADER true)

\echo '\n== Clientes exportados y etiquetas incluidas =='
SELECT count(*) AS clientes_con_operaciones,
       count(*) FILTER (WHERE e.perfil IS NOT NULL) AS con_anomalia
FROM v_features_cliente f JOIN cliente c USING (id_cliente) LEFT JOIN etiqueta e USING (codigo_cliente);

SELECT e.perfil, count(*) AS clientes
FROM etiqueta e JOIN cliente c USING (codigo_cliente)
JOIN v_features_cliente f USING (id_cliente)
GROUP BY e.perfil ORDER BY e.perfil;
