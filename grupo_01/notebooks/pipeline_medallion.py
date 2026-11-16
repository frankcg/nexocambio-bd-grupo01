# Databricks notebook source
# MAGIC %md
# MAGIC # NexoCambio · Pipeline medallion: de las operaciones crudas a las decisiones de negocio
# MAGIC
# MAGIC Parte 2 · Grupo 1. Un solo notebook recorre las tres capas de la arquitectura medallion sobre
# MAGIC tablas Delta y entrena el modelo de riesgo.
# MAGIC
# MAGIC | Capa | Tablas | Qué garantiza |
# MAGIC |---|---|---|
# MAGIC | **Bronze** | `bronze_operaciones`, `bronze_clientes`, `bronze_cuentas`, `bronze_etiquetas` | Copia fiel de los extractos de PostgreSQL, tal como llegan, con la fecha de carga y el archivo de origen |
# MAGIC | **Silver** | `silver_operaciones`, `silver_clientes`, `silver_operaciones_rechazadas` | Tipos correctos, sin duplicados, validadas; lo inválido se aparta en cuarentena |
# MAGIC | **Gold** | `gold_features_cliente`, `gold_clientes_riesgo`, `gold_exposicion_riesgo`, `gold_reactivacion` | Listas para el negocio: features, riesgo por cliente, exposición e ingresos a recuperar |
# MAGIC
# MAGIC - **Entrada:** los 4 archivos de `datos/bronze/` (los genera `generador/exportar_bronze.py`),
# MAGIC   subidos al *Volume* `nexocambio`, carpeta `bronze`. Bronze se carga **por lotes**; en producción
# MAGIC   vendría de los topics de Kafka con Structured Streaming.
# MAGIC - **Etiquetas:** las anomalías inyectadas por el generador **solo se usan para evaluar** el modelo.
# MAGIC - Fuera de Databricks corre con PySpark local (vistas en memoria en vez de tablas Delta, sin MLflow):
# MAGIC   `python notebooks/pipeline_medallion.py datos/bronze`

# COMMAND ----------

import sys

import numpy as np
import pandas as pd
from pyspark.sql import functions as F
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score

EN_DATABRICKS = "dbutils" in globals()
if EN_DATABRICKS:
    dbutils.widgets.text("ruta_bronze", "/Volumes/workspace/default/nexocambio/bronze")
    RUTA_BRONZE = dbutils.widgets.get("ruta_bronze")
    FORMATO = "delta"
    import mlflow
    import mlflow.sklearn
else:  # PySpark local, para validar el notebook antes de subirlo
    from pyspark.sql import SparkSession
    RUTA_BRONZE = sys.argv[1] if len(sys.argv) > 1 else "grupo_01/datos/bronze"
    ALMACEN = sys.argv[2] if len(sys.argv) > 2 else "spark-warehouse"
    spark = (SparkSession.builder.master("local[*]").appName("nexocambio-medallion")
             .config("spark.driver.memory", "4g").config("spark.sql.warehouse.dir", ALMACEN)
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.sql.execution.arrow.pyspark.enabled", "true")  # pandas ↔ Spark sin workers de Python
             .config("spark.sql.execution.arrow.pyspark.fallback.enabled", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    FORMATO, mlflow = "parquet", None

spark.conf.set("spark.sql.session.timeZone", "America/Lima")  # horas y días del negocio, como en PostgreSQL
CORTE = "TIMESTAMP '2026-10-22 00:00:00'"                       # fecha de corte de la Parte 1
SEMILLA, REVISION_ALTO, REVISION_MEDIO = 42, 0.02, 0.10
FEATURES = ["operaciones_30d", "monto_promedio_usd_90d", "dias_desde_ultima_operacion", "ratio_rechazo",
            "ratio_cerca_umbral_90d", "ratio_cuentas_terceros", "variacion_monto_30d", "ratio_nocturno"]
# El modelo mira cómo opera el cliente, no cuánto opera: con las de tamaño marcaba a los clientes grandes.
FEATURES_MODELO = ["ratio_rechazo", "ratio_cerca_umbral_90d", "ratio_cuentas_terceros",
                   "variacion_monto_30d", "ratio_nocturno"]


def guardar(df, tabla):
    if EN_DATABRICKS:
        df.write.mode("overwrite").option("overwriteSchema", "true").format(FORMATO).saveAsTable(tabla)
    else:  # en Windows, escribir tablas exige utilidades de Hadoop: localmente basta una vista en memoria
        df.cache().createOrReplaceTempView(tabla)
    print(f"  {tabla:<32}{spark.table(tabla).count():>10,} filas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze: los datos tal como llegan
# MAGIC
# MAGIC Todo se guarda como texto, sin transformar. Si mañana cambia una regla de negocio, se
# MAGIC recalcula desde aquí sin volver a consultar PostgreSQL.

# COMMAND ----------

print("Bronze")
for nombre in ["operaciones", "clientes", "cuentas", "etiquetas"]:
    crudo = (spark.read.option("header", True).csv(f"{RUTA_BRONZE}/{nombre}.csv.gz")
             .select("*", F.col("_metadata.file_name").alias("_archivo"))
             .withColumn("_fecha_carga", F.current_timestamp()))
    guardar(crudo, f"bronze_{nombre}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Silver: datos limpios y validados
# MAGIC
# MAGIC - Tipos correctos (`try_cast`: un valor ilegible queda nulo en vez de romper la carga).
# MAGIC - Sin duplicados por clave.
# MAGIC - Reglas de calidad: monto positivo, estado válido y fecha anterior al corte. Las operaciones
# MAGIC   que no las cumplen van a `silver_operaciones_rechazadas` (cuarentena), no se pierden.
# MAGIC - Se agrega lo que necesitan las features: si la cuenta destino es de un tercero y la hora local.

# COMMAND ----------

print("Silver")
clientes = spark.sql("""
    SELECT try_cast(id_cliente AS BIGINT) AS id_cliente, codigo_cliente, tipo_cliente,
           try_cast(fecha_registro_utc AS TIMESTAMP) AS fecha_registro, nombre,
           try_cast(es_pep AS BOOLEAN) AS es_pep
    FROM bronze_clientes""").dropDuplicates(["id_cliente"])
guardar(clientes, "silver_clientes")

ESTADOS = "('Pendiente de comprobante', 'Pendiente de validación', 'En proceso', 'Procesada', 'Rechazada')"
operaciones = spark.sql(f"""
    WITH tipadas AS (
        SELECT try_cast(o.id_operacion AS BIGINT) AS id_operacion, o.codigo_operacion,
               try_cast(o.id_cliente AS BIGINT) AS id_cliente, o.estado_actual,
               try_cast(o.fecha_operacion_utc AS TIMESTAMP) AS fecha_operacion,
               try_cast(o.id_cuenta_destino AS BIGINT) AS id_cuenta_destino, o.modalidad,
               o.moneda_origen, o.moneda_destino,
               try_cast(o.monto_usd AS DECIMAL(18, 2)) AS monto_usd,
               try_cast(o.spread_aplicado AS DECIMAL(6, 5)) AS spread_aplicado,
               try_cast(o.tasa_preferencial AS BOOLEAN) AS tasa_preferencial,
               row_number() OVER (PARTITION BY o.id_operacion ORDER BY o._fecha_carga DESC) AS copia
        FROM bronze_operaciones o
    )
    SELECT t.* EXCEPT (copia),
           cc.tipo AS tipo_destino,
           cc.tipo = 'banco' AND cc.titular <> c.nombre AS es_tercero,
           hour(t.fecha_operacion) AS hora_local,
           t.monto_usd > 0 AND t.estado_actual IN {ESTADOS} AND t.fecha_operacion < {CORTE}
               AND c.id_cliente IS NOT NULL AND cc.id_cuenta IS NOT NULL AS valida
    FROM tipadas t
    LEFT JOIN (SELECT try_cast(id_cuenta AS BIGINT) AS id_cuenta, tipo, titular FROM bronze_cuentas) cc
           ON cc.id_cuenta = t.id_cuenta_destino
    LEFT JOIN silver_clientes c ON c.id_cliente = t.id_cliente
    WHERE t.copia = 1""")
guardar(operaciones.filter("valida").drop("valida"), "silver_operaciones")
guardar(operaciones.filter("NOT valida OR valida IS NULL").drop("valida"), "silver_operaciones_rechazadas")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Gold · features por cliente (Spark SQL)
# MAGIC
# MAGIC La misma definición que la vista `v_features_cliente` de PostgreSQL (Parte 1). Los ratios se
# MAGIC calculan en decimal, como en PostgreSQL, para que el redondeo coincida.

# COMMAND ----------

print("Gold")
features = spark.sql(f"""
    SELECT o.id_cliente, c.codigo_cliente, c.tipo_cliente, c.es_pep,
           round((unix_micros({CORTE}) - unix_micros(c.fecha_registro)) / 86400e6) AS antiguedad_dias,
           count_if(o.fecha_operacion >= {CORTE} - INTERVAL 30 DAYS) AS operaciones_30d,
           round(avg(CASE WHEN o.fecha_operacion >= {CORTE} - INTERVAL 90 DAYS THEN o.monto_usd END), 2)
               AS monto_promedio_usd_90d,
           round((unix_micros({CORTE}) - unix_micros(max(o.fecha_operacion))) / 86400e6) AS dias_desde_ultima_operacion,
           round(CAST(count_if(o.estado_actual = 'Rechazada') AS DECIMAL(20, 10))
                 / nullif(count_if(o.estado_actual IN ('Procesada', 'Rechazada')), 0), 3) AS ratio_rechazo,
           round(avg(CASE WHEN o.fecha_operacion >= {CORTE} - INTERVAL 90 DAYS
                          THEN CAST(CASE WHEN o.monto_usd >= 9000 AND o.monto_usd < 10000 THEN 1 ELSE 0 END
                                    AS DECIMAL(20, 10)) END), 3) AS ratio_cerca_umbral_90d,
           round(avg(CASE WHEN o.tipo_destino = 'banco'
                          THEN CAST(CASE WHEN o.es_tercero THEN 1 ELSE 0 END AS DECIMAL(20, 10)) END), 3)
               AS ratio_cuentas_terceros,
           round(avg(CASE WHEN o.fecha_operacion >= {CORTE} - INTERVAL 30 DAYS THEN o.monto_usd END)
                 / nullif(avg(CASE WHEN o.fecha_operacion < {CORTE} - INTERVAL 30 DAYS
                                    AND o.fecha_operacion >= {CORTE} - INTERVAL 120 DAYS THEN o.monto_usd END), 0), 2)
               AS variacion_monto_30d,
           round(avg(CAST(CASE WHEN o.hora_local < 5 THEN 1 ELSE 0 END AS DECIMAL(20, 10))), 3) AS ratio_nocturno
    FROM silver_operaciones o
    JOIN silver_clientes c ON c.id_cliente = o.id_cliente
    GROUP BY o.id_cliente, c.codigo_cliente, c.tipo_cliente, c.es_pep, c.fecha_registro""")
guardar(features, "gold_features_cliente")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Control: ¿son las mismas features que en PostgreSQL?
# MAGIC
# MAGIC Se comparan con las sumas de control que imprime `generador/exportar_bronze.py`
# MAGIC (`resultados/09_bronze_y_control_postgresql.txt`).

# COMMAND ----------

control = spark.table("gold_features_cliente").agg(
    F.count("*").alias("clientes"),
    *[x for f in FEATURES for x in (F.count(f).alias(f"n_{f}"), F.round(F.sum(f), 3).alias(f"s_{f}"))]).first()
print(f"Sumas de control de gold_features_cliente (Spark):\n  clientes: {control['clientes']:,}")
for f in FEATURES:
    print(f"  {f:<30} no nulos {control[f'n_{f}']:>7,}   suma {float(control[f's_{f}']):>18,.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Gold · riesgo por cliente (modelo)
# MAGIC
# MAGIC **Isolation Forest** no supervisado sobre las 5 features de comportamiento. Riesgo **ALTO** = el
# MAGIC 2 % de clientes con mayor score (lo que revisa el back-office); **MEDIO** = hasta el 10 %.

# COMMAND ----------

pdf = spark.table("gold_features_cliente").orderBy("codigo_cliente").toPandas()
for f in FEATURES:
    pdf[f] = pd.to_numeric(pdf[f]).astype("float64")
X = pdf[FEATURES_MODELO].copy()
X["ratio_rechazo"] = X["ratio_rechazo"].fillna(0)         # sin operaciones decididas: sin rechazos
X["variacion_monto_30d"] = X["variacion_monto_30d"].fillna(1)  # sin historial previo: sin cambio
X = X.fillna(0)

PARAMS = {"n_estimators": 300, "max_samples": 1024, "contamination": "auto", "random_state": SEMILLA}
modelo = IsolationForest(**PARAMS).fit(X)
pdf["score_riesgo"] = -modelo.score_samples(X)
puesto = pdf["score_riesgo"].rank(ascending=False, method="first")
pdf["nivel_riesgo"] = np.where(puesto <= round(len(pdf) * REVISION_ALTO), "ALTO",
                               np.where(puesto <= round(len(pdf) * REVISION_MEDIO), "MEDIO", "NORMAL"))
p99 = X.quantile(0.99)
pdf["motivos"] = [", ".join(f"{f}={x[f]:g}" for f in FEATURES_MODELO if x[f] > p99[f])
                  for _, x in X.iterrows()]

riesgo = spark.createDataFrame(pdf[["id_cliente", "codigo_cliente", "score_riesgo", "nivel_riesgo", "motivos"]
                                   + FEATURES_MODELO])
guardar(riesgo, "gold_clientes_riesgo")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Evaluación contra las anomalías inyectadas (las etiquetas solo se usan aquí)

# COMMAND ----------

etiquetas = spark.table("bronze_etiquetas").select("codigo_cliente", "perfil").toPandas()
ev = pdf.merge(etiquetas, on="codigo_cliente", how="left")
y = ev["perfil"].notna()
alto = ev["nivel_riesgo"] == "ALTO"
activos = ev["operaciones_30d"].rank(ascending=False, method="first") <= 100
metricas = {"clientes": len(ev), "anomalias": int(y.sum()), "revisados": int(alto.sum()),
            "detectados": int((alto & y).sum()), "precision": (alto & y).sum() / alto.sum(),
            "recall": (alto & y).sum() / y.sum(), "roc_auc": roc_auc_score(y, ev["score_riesgo"]),
            "grandes_legitimos": int((activos & ~y).sum()),
            "grandes_legitimos_marcados": int((activos & ~y & alto).sum())}
print(f"Clientes: {metricas['clientes']:,} · con anomalía inyectada: {metricas['anomalias']}")
print(f"Riesgo ALTO (top 2 %): {metricas['revisados']} revisados · {metricas['detectados']} detectados · "
      f"precisión {metricas['precision']:.1%} · recall {metricas['recall']:.1%} · ROC AUC {metricas['roc_auc']:.3f}")
print(f"Clientes grandes legítimos marcados: {metricas['grandes_legitimos_marcados']} de {metricas['grandes_legitimos']}")
por_perfil = ev[y].groupby("perfil").agg(clientes=("codigo_cliente", "count"), detecta=("nivel_riesgo",
                                                                                       lambda s: (s == "ALTO").mean()))
print(por_perfil.to_string(formatters={"detecta": "{:.1%}".format}))
for perfil, fila in por_perfil.iterrows():
    metricas[f"recall_{perfil}"] = fila["detecta"]

if mlflow is not None:
    mlflow.set_experiment("/Shared/nexocambio_anomalias")
    with mlflow.start_run(run_name="isolation_forest_medallion"):
        mlflow.log_params({**PARAMS, "features": ",".join(FEATURES_MODELO), "fuente": "gold_features_cliente"})
        mlflow.log_metrics({k: float(v) for k, v in metricas.items()})
        mlflow.sklearn.log_model(modelo, name="modelo", input_example=X.head(5))
    print("Run registrado en MLflow.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Gold · exposición del negocio al riesgo (últimos 90 días)
# MAGIC
# MAGIC ¿Qué parte del volumen y del ingreso por spread viene de clientes de riesgo ALTO?

# COMMAND ----------

exposicion = spark.sql(f"""
    SELECT r.nivel_riesgo, count(DISTINCT o.id_cliente) AS clientes, count(*) AS operaciones,
           round(sum(o.monto_usd)) AS volumen_usd, round(sum(o.monto_usd * o.spread_aplicado)) AS spread_usd,
           round(100 * sum(o.monto_usd) / sum(sum(o.monto_usd)) OVER (), 1) AS pct_volumen,
           round(100 * sum(o.monto_usd * o.spread_aplicado) / sum(sum(o.monto_usd * o.spread_aplicado)) OVER (), 1)
               AS pct_spread
    FROM silver_operaciones o
    JOIN gold_clientes_riesgo r ON r.id_cliente = o.id_cliente
    WHERE o.estado_actual = 'Procesada' AND o.fecha_operacion >= {CORTE} - INTERVAL 90 DAYS
    GROUP BY r.nivel_riesgo""")
guardar(exposicion, "gold_exposicion_riesgo")
print(spark.table("gold_exposicion_riesgo").orderBy("nivel_riesgo").toPandas().to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Gold · clientes a reactivar
# MAGIC
# MAGIC Clientes frecuentes (5 operaciones o más) que llevan más del doble de su intervalo habitual sin
# MAGIC operar (y al menos 14 días, para no alertar por un cliente diario que descansó un fin de semana),
# MAGIC pero menos de 120 días: todavía se pueden recuperar. Se ordenan por el spread mensual
# MAGIC que generaban, y **no se contacta a los de riesgo ALTO**.

# COMMAND ----------

clientes_frecuentes = spark.sql(f"""
    WITH ops AS (
        SELECT id_cliente, fecha_operacion, monto_usd * spread_aplicado AS spread,
               lag(fecha_operacion) OVER (PARTITION BY id_cliente ORDER BY fecha_operacion) AS anterior
        FROM silver_operaciones WHERE estado_actual = 'Procesada'
    ), cli AS (
        SELECT id_cliente, count(*) AS operaciones, max(fecha_operacion) AS ultima_operacion,
               avg((unix_micros(fecha_operacion) - unix_micros(anterior)) / 86400e6) AS intervalo_habitual_dias,
               (unix_micros({CORTE}) - unix_micros(max(fecha_operacion))) / 86400e6 AS dias_inactivo,
               sum(spread) / greatest((unix_micros(max(fecha_operacion)) - unix_micros(min(fecha_operacion)))
                                      / 86400e6 / 30.4, 1) AS spread_mensual_usd
        FROM ops GROUP BY id_cliente HAVING count(*) >= 5
    )
    SELECT cli.*, CASE WHEN dias_inactivo <= greatest(2 * intervalo_habitual_dias, 14) THEN 'Activo'
                       WHEN dias_inactivo <= 120 THEN 'En riesgo' ELSE 'Abandono' END AS segmento
    FROM cli""")
clientes_frecuentes.createOrReplaceTempView("clientes_frecuentes")
print(spark.sql("""SELECT segmento, count(*) AS clientes, round(avg(dias_inactivo)) AS dias_inactivo_prom,
                          round(sum(spread_mensual_usd)) AS spread_mensual_cuando_activos_usd
                   FROM clientes_frecuentes GROUP BY segmento ORDER BY segmento""").toPandas().to_string(index=False))

reactivacion = spark.sql("""
    SELECT r.codigo_cliente, f.operaciones, round(f.intervalo_habitual_dias, 1) AS intervalo_habitual_dias,
           round(f.dias_inactivo) AS dias_inactivo, round(f.spread_mensual_usd, 2) AS spread_mensual_usd,
           f.ultima_operacion, r.nivel_riesgo, r.nivel_riesgo <> 'ALTO' AS contactar
    FROM clientes_frecuentes f JOIN gold_clientes_riesgo r ON r.id_cliente = f.id_cliente
    WHERE f.segmento = 'En riesgo'""")
guardar(reactivacion, "gold_reactivacion")
print(spark.sql("""SELECT contactar, count(*) AS clientes, round(sum(spread_mensual_usd)) AS spread_mensual_usd
                   FROM gold_reactivacion GROUP BY contactar ORDER BY contactar DESC""").toPandas().to_string(index=False))
print(spark.sql("""SELECT * FROM gold_reactivacion WHERE contactar ORDER BY spread_mensual_usd DESC LIMIT 10""")
      .toPandas().to_string(index=False))
