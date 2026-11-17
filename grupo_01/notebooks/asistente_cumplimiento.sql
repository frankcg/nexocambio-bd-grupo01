-- Databricks notebook source
-- MAGIC %md
-- MAGIC # NexoCambio · Asistente de cumplimiento (AI Playground)
-- MAGIC
-- MAGIC Parte 2 · Grupo 1. Crea cuatro **funciones de Unity Catalog** sobre las tablas gold del
-- MAGIC pipeline medallion. En **AI Playground** se agregan como *herramientas* de un modelo de lenguaje:
-- MAGIC el modelo decide cuál llamar y responde en lenguaje de negocio con cifras reales, sin inventarlas.
-- MAGIC
-- MAGIC | Función | Responde |
-- MAGIC |---|---|
-- MAGIC | `riesgo_cliente(p_codigo)` | ¿Por qué este cliente tiene este nivel de riesgo? |
-- MAGIC | `clientes_mayor_riesgo(p_cantidad)` | ¿A quién debe revisar primero cumplimiento? |
-- MAGIC | `exposicion_riesgo()` | ¿Qué parte del negocio pasa por clientes riesgosos? |
-- MAGIC | `clientes_a_reactivar(p_cantidad)` | ¿A quién debe llamar el área comercial esta semana? |
-- MAGIC
-- MAGIC Requiere haber ejecutado antes `pipeline_medallion` (las tablas gold).

-- COMMAND ----------

CREATE OR REPLACE FUNCTION workspace.default.riesgo_cliente(
  p_codigo STRING COMMENT 'Código del cliente, con el formato CLI-XXXXXX (por ejemplo CLI-ZYCHEZ)')
RETURNS TABLE (
  codigo_cliente STRING, nivel_riesgo STRING, score_riesgo DOUBLE, motivos STRING,
  operaciones_30d BIGINT, monto_promedio_usd_90d DOUBLE, dias_desde_ultima_operacion DOUBLE,
  ratio_cerca_umbral_90d DOUBLE, ratio_cuentas_terceros DOUBLE, ratio_nocturno DOUBLE,
  ratio_rechazo DOUBLE, variacion_monto_30d DOUBLE)
COMMENT 'Nivel de riesgo de un cliente de NexoCambio (ALTO = top 2 %, MEDIO = hasta el top 10 %, NORMAL), su score del modelo Isolation Forest, los motivos (features por encima del percentil 99) y sus 8 features de comportamiento. ratio_cerca_umbral_90d es la proporción de operaciones entre US$ 9 000 y 9 999 en 90 días (fraccionamiento bajo el umbral de registro de la UIF); ratio_cuentas_terceros, la proporción enviada a cuentas de otros titulares; ratio_nocturno, la proporción entre las 0 y las 5 a. m.'
RETURN
  SELECT r.codigo_cliente, r.nivel_riesgo, r.score_riesgo, r.motivos,
         f.operaciones_30d, CAST(f.monto_promedio_usd_90d AS DOUBLE), CAST(f.dias_desde_ultima_operacion AS DOUBLE),
         CAST(f.ratio_cerca_umbral_90d AS DOUBLE), CAST(f.ratio_cuentas_terceros AS DOUBLE),
         CAST(f.ratio_nocturno AS DOUBLE), CAST(f.ratio_rechazo AS DOUBLE), CAST(f.variacion_monto_30d AS DOUBLE)
  FROM workspace.default.gold_clientes_riesgo r
  JOIN workspace.default.gold_features_cliente f ON f.id_cliente = r.id_cliente
  WHERE r.codigo_cliente = upper(trim(p_codigo));

-- COMMAND ----------

CREATE OR REPLACE FUNCTION workspace.default.clientes_mayor_riesgo(
  p_cantidad INT COMMENT 'Cuántos clientes devolver (por ejemplo 10)')
RETURNS TABLE (puesto INT, codigo_cliente STRING, nivel_riesgo STRING, score_riesgo DOUBLE, motivos STRING)
COMMENT 'Los clientes de NexoCambio con mayor score de riesgo, en orden: es la lista que el área de cumplimiento debe revisar primero. El modelo prioriza; la decisión final es siempre de un analista.'
RETURN
  SELECT CAST(puesto AS INT), codigo_cliente, nivel_riesgo, score_riesgo, motivos
  FROM (SELECT *, row_number() OVER (ORDER BY score_riesgo DESC) AS puesto
        FROM workspace.default.gold_clientes_riesgo)
  WHERE puesto <= p_cantidad;

-- COMMAND ----------

CREATE OR REPLACE FUNCTION workspace.default.exposicion_riesgo()
RETURNS TABLE (nivel_riesgo STRING, clientes BIGINT, operaciones BIGINT, volumen_usd DOUBLE,
               spread_usd DOUBLE, pct_volumen DOUBLE, pct_spread DOUBLE)
COMMENT 'Exposición del negocio al riesgo en los últimos 90 días: por nivel de riesgo (ALTO, MEDIO, NORMAL), cuántos clientes y operaciones procesadas hay, el volumen en dólares, el ingreso por spread y qué porcentaje del total representan.'
RETURN
  SELECT nivel_riesgo, clientes, operaciones, CAST(volumen_usd AS DOUBLE), CAST(spread_usd AS DOUBLE),
         CAST(pct_volumen AS DOUBLE), CAST(pct_spread AS DOUBLE)
  FROM workspace.default.gold_exposicion_riesgo;

-- COMMAND ----------

CREATE OR REPLACE FUNCTION workspace.default.clientes_a_reactivar(
  p_cantidad INT COMMENT 'Cuántos clientes devolver (por ejemplo 10)')
RETURNS TABLE (codigo_cliente STRING, operaciones BIGINT, intervalo_habitual_dias DOUBLE, dias_inactivo DOUBLE,
               spread_mensual_usd DOUBLE, nivel_riesgo STRING)
COMMENT 'Clientes frecuentes que se están enfriando (llevan más del doble de su intervalo habitual y al menos 14 días sin operar, pero menos de 120), ordenados por el spread mensual que generaban. Excluye a los clientes de riesgo ALTO: a ellos no se les ofrecen incentivos.'
RETURN
  SELECT codigo_cliente, operaciones, CAST(intervalo_habitual_dias AS DOUBLE), CAST(dias_inactivo AS DOUBLE),
         CAST(spread_mensual_usd AS DOUBLE), nivel_riesgo
  FROM (SELECT *, row_number() OVER (ORDER BY spread_mensual_usd DESC) AS puesto
        FROM workspace.default.gold_reactivacion WHERE contactar)
  WHERE puesto <= p_cantidad;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Prueba de las funciones

-- COMMAND ----------

SELECT * FROM workspace.default.riesgo_cliente('CLI-ZYCHEZ');

-- COMMAND ----------

SELECT * FROM workspace.default.clientes_mayor_riesgo(5);

-- COMMAND ----------

SELECT * FROM workspace.default.exposicion_riesgo();

-- COMMAND ----------

SELECT * FROM workspace.default.clientes_a_reactivar(5);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## Configuración en AI Playground
-- MAGIC
-- MAGIC 1. Menú izquierdo → **AI/ML → Playground**.
-- MAGIC 2. Elegir un modelo que admita herramientas (en el selector aparecen marcados como *Tools enabled*).
-- MAGIC 3. **Tools → Add tool → Hosted function** y agregar las cuatro funciones de `workspace.default`:
-- MAGIC    `riesgo_cliente`, `clientes_mayor_riesgo`, `exposicion_riesgo` y `clientes_a_reactivar`.
-- MAGIC 4. Pegar en **System prompt**:
-- MAGIC
-- MAGIC > Eres el asistente de cumplimiento y del área comercial de NexoCambio, una casa de cambio
-- MAGIC > digital peruana. Responde en español, de forma breve y en lenguaje de negocio. Usa siempre las
-- MAGIC > herramientas para obtener cifras y nunca inventes datos ni clientes. Al explicar un riesgo,
-- MAGIC > traduce las features: ratio_cerca_umbral_90d alto significa fraccionar operaciones justo bajo
-- MAGIC > US$ 10 000, el umbral de registro de la UIF; ratio_cuentas_terceros, enviar a cuentas de otras
-- MAGIC > personas; ratio_nocturno, operar de madrugada. Recuerda que el modelo prioriza y la decisión
-- MAGIC > final es de un analista. Los datos son ficticios, generados para un curso.
-- MAGIC
-- MAGIC 5. Preguntas para la demo:
-- MAGIC    - *¿Por qué CLI-ZYCHEZ es un cliente de riesgo alto?*
-- MAGIC    - *¿Qué parte de nuestro ingreso por spread viene de clientes de riesgo alto?*
-- MAGIC    - *¿Cuáles son los 5 clientes que cumplimiento debería revisar primero y qué tienen en común?*
-- MAGIC    - *Redacta un borrador de reporte de operación sospechosa (ROS) para CLI-ZYCHEZ.*
-- MAGIC    - *¿A qué 5 clientes debería llamar el área comercial esta semana?*
-- MAGIC
-- MAGIC Para ver qué herramienta usó el modelo y con qué argumentos, expandir la llamada en la respuesta.
