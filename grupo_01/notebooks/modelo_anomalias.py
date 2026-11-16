# Databricks notebook source
# MAGIC %md
# MAGIC # NexoCambio · Modelo de detección de operaciones inusuales
# MAGIC
# MAGIC Parte 2 · Grupo 1. Entrena un **Isolation Forest** (no supervisado) con las 5 features de
# MAGIC **comportamiento** de `v_features_cliente` (Parte 1) y mide cuántos de los clientes con
# MAGIC comportamiento inusual inyectado detecta. Las 3 features de tamaño o actividad
# MAGIC (operaciones, ticket y recencia) se dejan fuera: con ellas el modelo confundía a los clientes
# MAGIC grandes legítimos con clientes inusuales.
# MAGIC
# MAGIC - **Entrada:** `features_clientes.csv`, exportado de PostgreSQL con `sql/07_exportar_features.sql`
# MAGIC   (35 438 clientes). En Databricks se sube a un *Volume* de Unity Catalog.
# MAGIC - **Etiquetas:** la columna `perfil_anomalia` (pitufeo, pico, multicuenta, nocturno) **no se usa
# MAGIC   para entrenar**; solo para evaluar.
# MAGIC - **Salida:** tabla Delta `features_clientes_scored` y experimento en MLflow.
# MAGIC
# MAGIC También se ejecuta fuera de Databricks para validarlo:
# MAGIC `python notebooks/modelo_anomalias.py datos/features_clientes.csv`

# COMMAND ----------

import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

try:
    import mlflow
    import mlflow.sklearn
except ImportError:  # fuera de Databricks, MLflow es opcional
    mlflow = None

EN_DATABRICKS = "dbutils" in globals()

if EN_DATABRICKS:
    dbutils.widgets.text("ruta_csv", "/Volumes/workspace/default/nexocambio/features_clientes.csv")
    RUTA_CSV = dbutils.widgets.get("ruta_csv")
else:
    RUTA_CSV = sys.argv[1] if len(sys.argv) > 1 else "grupo_01/datos/features_clientes.csv"

SEMILLA = 42
REVISION_PCT = 0.02  # el back-office revisa el 2 % de clientes más riesgosos

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Carga y preparación
# MAGIC
# MAGIC Los nulos tienen significado de negocio: sin operaciones en 90 días no hay ticket promedio
# MAGIC (0), sin operaciones decididas no hay rechazos (0) y sin historial previo no hay variación (1 = sin cambio).

# COMMAND ----------

df = pd.read_csv(RUTA_CSV)

FEATURES = ["operaciones_30d", "monto_promedio_usd_90d", "dias_desde_ultima_operacion", "ratio_rechazo",
            "ratio_cerca_umbral_90d", "ratio_cuentas_terceros", "variacion_monto_30d", "ratio_nocturno"]

# El modelo mira cómo opera el cliente, no cuánto opera.
FEATURES_MODELO = ["ratio_rechazo", "ratio_cerca_umbral_90d", "ratio_cuentas_terceros",
                   "variacion_monto_30d", "ratio_nocturno"]

X = df[FEATURES].copy()
X["monto_promedio_usd_90d"] = X["monto_promedio_usd_90d"].fillna(0)
X["ratio_rechazo"] = X["ratio_rechazo"].fillna(0)
X["variacion_monto_30d"] = X["variacion_monto_30d"].fillna(1)
X = X.fillna(0).astype("float64")  # MLflow pide decimales para admitir nulos al predecir
X_modelo = X[FEATURES_MODELO]

y = df["perfil_anomalia"].notna().astype(int)  # solo para evaluar
print(f"Clientes: {len(df):,} · con anomalía inyectada: {y.sum()} ({y.mean():.2%})")
print(df["perfil_anomalia"].value_counts().to_string())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Entrenamiento (no supervisado)

# COMMAND ----------

PARAMS = {"n_estimators": 300, "max_samples": 1024, "contamination": "auto", "random_state": SEMILLA}

modelo = IsolationForest(**PARAMS).fit(X_modelo)
df["score_riesgo"] = -modelo.score_samples(X_modelo)  # más alto = más inusual

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Evaluación contra las anomalías inyectadas
# MAGIC
# MAGIC La pregunta de negocio: **si el back-office revisa solo el 2 % de clientes con mayor score,
# MAGIC ¿cuántos casos inusuales encuentra?** Se compara con una regla simple de una sola feature
# MAGIC (fraccionamiento: `ratio_cerca_umbral_90d` ≥ 0,5), del estilo de las reglas de la Parte 1.

# COMMAND ----------

k = int(round(len(df) * REVISION_PCT))
df["revisar_modelo"] = df["score_riesgo"].rank(ascending=False, method="first") <= k
df["revisar_regla"] = X["ratio_cerca_umbral_90d"] >= 0.5


def resumen(marca):
    tp = int((marca & (y == 1)).sum())
    return {"revisados": int(marca.sum()), "detectados": tp,
            "precision": tp / max(int(marca.sum()), 1), "recall": tp / int(y.sum())}


metricas = {
    "roc_auc": roc_auc_score(y, df["score_riesgo"]),
    "average_precision": average_precision_score(y, df["score_riesgo"]),
}
mod, reg = resumen(df["revisar_modelo"]), resumen(df["revisar_regla"])
metricas.update({f"modelo_{m}": v for m, v in mod.items()})
metricas.update({f"regla_{m}": v for m, v in reg.items()})

print(f"ROC AUC: {metricas['roc_auc']:.3f} · Average precision: {metricas['average_precision']:.3f}")
print(f"Top {REVISION_PCT:.0%} (k = {k}) · base de positivos: {y.mean():.2%}\n")
comparacion = pd.DataFrame([mod, reg], index=["Isolation Forest (top 2 %)", "Regla: ratio_cerca_umbral ≥ 0,5"])
print(comparacion.to_string(formatters={"precision": "{:.1%}".format, "recall": "{:.1%}".format}))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Detección por tipo de comportamiento inusual

# COMMAND ----------

por_perfil = (df[y == 1].groupby("perfil_anomalia")
              .agg(clientes=("codigo_cliente", "count"),
                   detecta_modelo=("revisar_modelo", "mean"),
                   detecta_regla=("revisar_regla", "mean")))
print(por_perfil.to_string(formatters={"detecta_modelo": "{:.1%}".format, "detecta_regla": "{:.1%}".format}))
for perfil, fila in por_perfil.iterrows():
    metricas[f"recall_{perfil}"] = fila["detecta_modelo"]

# COMMAND ----------

# MAGIC %md
# MAGIC ### ¿Marca a los buenos clientes grandes?
# MAGIC
# MAGIC Entre los 100 clientes más activos (por operaciones en 30 días), los que no tienen anomalía son
# MAGIC clientes grandes legítimos: marcarlos sería poner bajo sospecha a los mejores clientes.

# COMMAND ----------

activos = df["operaciones_30d"].rank(ascending=False, method="first") <= 100
grandes_legitimos = activos & (y == 0)
metricas["grandes_legitimos_marcados"] = int((grandes_legitimos & df["revisar_modelo"]).sum())
print(f"Clientes grandes legítimos marcados: {metricas['grandes_legitimos_marcados']} "
      f"de {int(grandes_legitimos.sum())} (entre los 100 más activos)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Los 10 clientes más riesgosos

# COMMAND ----------

top = df.sort_values("score_riesgo", ascending=False).head(10)
print(top[["codigo_cliente", "score_riesgo", "perfil_anomalia", "operaciones_30d"] + FEATURES_MODELO]
      .round(3).to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Registro en MLflow y tabla Delta
# MAGIC
# MAGIC El modelo queda versionado en MLflow (el servicio de scoring cargaría esa versión) y los
# MAGIC scores se guardan como tabla Delta, la capa *gold* del Data Lake.

# COMMAND ----------

if mlflow is not None:
    mlflow.set_experiment("/Shared/nexocambio_anomalias" if EN_DATABRICKS else "nexocambio_anomalias")
    with mlflow.start_run(run_name="isolation_forest"):
        mlflow.log_params({**PARAMS, "features": ",".join(FEATURES_MODELO), "revision_pct": REVISION_PCT})
        mlflow.log_metrics({m: float(v) for m, v in metricas.items()})
        try:  # MLflow 3 (Databricks) usa name=; MLflow 2, artifact_path=
            mlflow.sklearn.log_model(modelo, name="modelo", input_example=X_modelo.head(5))
        except TypeError:
            mlflow.sklearn.log_model(modelo, artifact_path="modelo", input_example=X_modelo.head(5))
    print("Run registrado en MLflow.")

if EN_DATABRICKS:
    (spark.createDataFrame(df.drop(columns=["revisar_regla"]))
          .write.mode("overwrite").format("delta").saveAsTable("features_clientes_scored"))
    print("Tabla Delta features_clientes_scored creada.")
