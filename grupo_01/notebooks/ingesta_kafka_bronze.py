# Databricks notebook source
# MAGIC %md
# MAGIC # NexoCambio · Ingesta de Kafka a la capa bronze (Structured Streaming)
# MAGIC
# MAGIC Parte 2 · Grupo 1. Lee los eventos de los topics de Confluent Cloud y los guarda **tal como
# MAGIC llegan** en la tabla Delta `bronze_eventos_kafka`; luego los interpreta en
# MAGIC `silver_eventos_kafka`. Es el mismo flujo de eventos que alimenta a Redis en tiempo real: cada
# MAGIC operación o cotización publicada llega también al Data Lake.
# MAGIC
# MAGIC - **Disparador `availableNow`:** cada ejecución lee todo lo nuevo desde la última vez y se detiene.
# MAGIC   El *checkpoint* recuerda los offsets ya leídos, así que ningún evento se carga dos veces.
# MAGIC   Programado como Job, la ingesta queda automática.
# MAGIC - **Credenciales:** del *secret scope* `nexocambio` si existe; si no, de los widgets de abajo.
# MAGIC   Nunca se escriben en el código.
# MAGIC - Fuera de Databricks lee los mismos topics en modo batch con PySpark local (para validar):
# MAGIC   `python notebooks/ingesta_kafka_bronze.py ../.env <carpeta con los jars del conector de Kafka>`

# COMMAND ----------

import sys
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, DoubleType, LongType, StringType, StructField, StructType

TOPICS = "nexocambio.operaciones,nexocambio.cotizaciones"
EN_DATABRICKS = "dbutils" in globals()

if EN_DATABRICKS:
    dbutils.widgets.text("kafka_bootstrap", "")
    dbutils.widgets.text("kafka_api_key", "")
    dbutils.widgets.text("kafka_api_secret", "")
    dbutils.widgets.text("checkpoint", "/Volumes/workspace/default/nexocambio/checkpoints/bronze_eventos_kafka")

    def credencial(nombre):
        try:
            return dbutils.secrets.get("nexocambio", nombre)
        except Exception:
            return dbutils.widgets.get(nombre)

    BOOTSTRAP, API_KEY, API_SECRET = (credencial(n) for n in ("kafka_bootstrap", "kafka_api_key", "kafka_api_secret"))
    CHECKPOINT = dbutils.widgets.get("checkpoint")
    LOGIN = "kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule"  # Kafka empaquetado en Databricks
else:  # PySpark local, para validar la conexión y el esquema antes de subir el notebook
    from pyspark.sql import SparkSession
    env = dict(l.split("=", 1) for l in Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
               .read_text(encoding="utf-8").splitlines() if "=" in l and not l.lstrip().startswith("#"))
    BOOTSTRAP, API_KEY, API_SECRET = (env[k].strip().strip('"') for k in
                                      ("KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET"))
    # Carpeta con spark-sql-kafka, spark-token-provider-kafka, kafka-clients y commons-pool2. En Windows
    # se pasan por el classpath: descargarlos con spark.jars.packages exige las utilidades de Hadoop.
    JARS = sys.argv[2] if len(sys.argv) > 2 else "kafkajars"
    spark = (SparkSession.builder.master("local[*]").appName("nexocambio-ingesta")
             .config("spark.driver.extraClassPath", f"{JARS}/*")
             .config("spark.sql.execution.arrow.pyspark.enabled", "true").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    LOGIN = "org.apache.kafka.common.security.plain.PlainLoginModule"

spark.conf.set("spark.sql.session.timeZone", "America/Lima")  # horas del negocio, como en el resto del proyecto

if not (BOOTSTRAP and API_KEY and API_SECRET):
    raise ValueError("Faltan las credenciales de Kafka: complete los widgets o cree el secret scope 'nexocambio'.")

OPCIONES_KAFKA = {
    "kafka.bootstrap.servers": BOOTSTRAP,
    "kafka.security.protocol": "SASL_SSL",
    "kafka.sasl.mechanism": "PLAIN",
    "kafka.sasl.jaas.config": f'{LOGIN} required username="{API_KEY}" password="{API_SECRET}";',
    "subscribe": TOPICS,
    "startingOffsets": "earliest",  # la primera vez trae todo lo retenido (7 días); luego, el checkpoint manda
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Bronze: el evento crudo, con su origen en Kafka

# COMMAND ----------

def a_bronze(df):
    return df.select(
        "topic", "partition", "offset",
        F.col("timestamp").alias("fecha_kafka"),
        F.col("key").cast("string").alias("clave"),
        F.col("value").cast("string").alias("evento_json"),
        F.current_timestamp().alias("_fecha_carga"))


if EN_DATABRICKS:
    consulta = (a_bronze(spark.readStream.format("kafka").options(**OPCIONES_KAFKA).load())
                .writeStream.format("delta").option("checkpointLocation", CHECKPOINT)
                .trigger(availableNow=True).toTable("bronze_eventos_kafka"))
    consulta.awaitTermination()
    print(f"Ingesta terminada. bronze_eventos_kafka: {spark.table('bronze_eventos_kafka').count():,} eventos")
    bronze = spark.table("bronze_eventos_kafka")
else:
    bronze = a_bronze(spark.read.format("kafka").options(**OPCIONES_KAFKA).load())
    print(f"Eventos leídos de Confluent Cloud: {bronze.count():,}")

bronze.groupBy("topic").agg(F.count("*").alias("eventos"), F.max("fecha_kafka").alias("ultimo")).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Silver: el evento interpretado
# MAGIC
# MAGIC Se lee el JSON con un esquema explícito (el contrato de eventos de `modelo_nosql.pdf`) y se deja
# MAGIC una fila por evento, sin duplicados (Kafka entrega *at-least-once*).

# COMMAND ----------

CUENTA = StructType([StructField("id_cuenta", LongType()), StructField("tipo", StringType()),
                     StructField("titular_es_cliente", BooleanType())])
EVENTO = StructType([
    StructField("tipo_evento", StringType()), StructField("id_evento", StringType()),
    StructField("ocurrido_en", StringType()),
    StructField("operacion", StructType([
        StructField("codigo_operacion", StringType()), StructField("codigo_cotizacion", StringType()),
        StructField("id_cliente", LongType()), StructField("monto_usd", DoubleType()),
        StructField("estado", StringType()), StructField("cuenta_destino", CUENTA)])),
    StructField("cotizacion", StructType([
        StructField("codigo_cotizacion", StringType()), StructField("id_cliente", LongType()),
        StructField("codigo_cliente", StringType()), StructField("monto_usd", DoubleType()),
        StructField("tasa_preferencial", BooleanType()), StructField("vigencia_s", LongType())])),
])

e = bronze.withColumn("e", F.from_json("evento_json", EVENTO))
silver = (e.select(
              "topic", "partition", "offset", "fecha_kafka",
              F.col("e.tipo_evento").alias("tipo_evento"), F.col("e.id_evento").alias("id_evento"),
              F.to_timestamp("e.ocurrido_en").alias("ocurrido_en"),
              F.coalesce("e.operacion.id_cliente", "e.cotizacion.id_cliente").alias("id_cliente"),
              F.col("e.operacion.codigo_operacion").alias("codigo_operacion"),
              F.coalesce("e.operacion.codigo_cotizacion", "e.cotizacion.codigo_cotizacion").alias("codigo_cotizacion"),
              F.coalesce("e.operacion.monto_usd", "e.cotizacion.monto_usd").alias("monto_usd"),
              F.col("e.operacion.cuenta_destino.tipo").alias("tipo_destino"),
              F.col("e.operacion.cuenta_destino.titular_es_cliente").alias("titular_es_cliente"))
          .dropDuplicates(["id_evento"]))

if EN_DATABRICKS:
    silver.write.mode("overwrite").format("delta").saveAsTable("silver_eventos_kafka")
    silver = spark.table("silver_eventos_kafka")
print(f"silver_eventos_kafka: {silver.count():,} eventos")
silver.orderBy(F.col("fecha_kafka").desc()).select(
    "tipo_evento", "ocurrido_en", "id_cliente", "codigo_operacion", "codigo_cotizacion", "monto_usd",
    "topic", "partition", "offset").show(10, truncate=False)
