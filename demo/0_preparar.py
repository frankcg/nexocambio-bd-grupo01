"""
NexoCambio · Demo, paso 0: preparar el entorno (se ejecuta una vez, antes de la exposición).

1. Crea los topics en Confluent Cloud (si no existen).
2. Carga Redis desde PostgreSQL, como lo haría el job nocturno (perfil batch) más la
   reconstrucción de ventanas: perfil, contadores diarios, operaciones de 7 días y destinos.
3. Entrena el modelo (Isolation Forest, mismos parámetros y semilla que en Databricks).

    .venv\\Scripts\\python demo/0_preparar.py
"""
import pickle
import time

import numpy as np
import pandas as pd
from confluent_kafka.admin import AdminClient, NewTopic
from sklearn.ensemble import IsolationForest

from comun import (CORTE, FEATURES_MODELO, MODELO, TOPICS, clave, conectar_postgres, conectar_redis,
                   kafka_conf, vector)


def crear_topics():
    admin = AdminClient(kafka_conf())
    existentes = admin.list_topics(timeout=20).topics
    nuevos = [NewTopic(nombre, num_partitions=part, replication_factor=3,
                       config={"cleanup.policy": "compact"} if compactado else {"retention.ms": str(7 * 86_400_000)})
              for nombre, (part, compactado) in TOPICS.items() if nombre not in existentes]
    for nombre, futuro in (admin.create_topics(nuevos) if nuevos else {}).items():
        futuro.result()
        print(f"  topic creado: {nombre}")
    print(f"  topics en Confluent Cloud: {', '.join(sorted(TOPICS))}")


# Ordenado por código de cliente: el mismo orden de filas que el notebook de Databricks, para que
# el Isolation Forest (que submuestrea según el orden) salga idéntico.
SQL_PERFIL = """
SELECT f.id_cliente, c.codigo_cliente, f.tipo_cliente, f.es_pep, f.antiguedad_dias, f.ratio_rechazo,
       f.ratio_cerca_umbral_90d, f.ratio_cuentas_terceros, f.variacion_monto_30d, f.ratio_nocturno,
       (extract(epoch FROM u.ultima) * 1000)::bigint AS ultima_operacion
FROM v_features_cliente f
JOIN cliente c USING (id_cliente)
JOIN (SELECT id_cliente, max(fecha_operacion) AS ultima FROM operacion
      WHERE fecha_operacion < %(corte)s GROUP BY id_cliente) u USING (id_cliente)
ORDER BY c.codigo_cliente
"""

SQL_OPS = """
WITH nombre_cliente AS (
    SELECT id_cliente, nombres || ' ' || apellidos AS nombre FROM persona_natural
    UNION ALL
    SELECT id_cliente, razon_social FROM empresa
)
SELECT v.id_cliente, v.codigo_operacion, v.id_cuenta_destino, v.monto_usd,
       to_char(v.fecha_operacion, 'YYYYMMDD') AS dia,
       (extract(epoch FROM v.fecha_operacion) * 1000)::bigint AS ts_ms,
       extract(hour FROM v.fecha_operacion) < 5 AS nocturna,
       coalesce(cc.tipo = 'banco' AND cc.titular <> n.nombre, false) AS tercero
FROM v_operacion v
JOIN cuenta_cliente cc ON cc.id_cuenta = v.id_cuenta_destino
JOIN nombre_cliente n  ON n.id_cliente = v.id_cliente
WHERE v.fecha_operacion >= %(corte)s - INTERVAL '120 days' AND v.fecha_operacion < %(corte)s
"""


class Lotes:
    """Pipeline que se envía cada 5 000 comandos (uno solo con 200 mil comandos satura el socket)."""

    def __init__(self, r, tamano=5000):
        self.p, self.tamano, self.pendientes = r.pipeline(transaction=False), tamano, 0

    def __getattr__(self, comando):
        def llamar(*args, **kwargs):
            getattr(self.p, comando)(*args, **kwargs)
            self.pendientes += 1
            if self.pendientes >= self.tamano:
                self.execute()
        return llamar

    def execute(self):
        self.p.execute()
        self.pendientes = 0


def cargar_redis():
    r = conectar_redis()
    r.flushdb()
    with conectar_postgres() as pg:
        t0 = time.perf_counter()
        cur = pg.execute(SQL_PERFIL, {"corte": CORTE})
        perfiles = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        ops = pd.DataFrame(pg.execute(SQL_OPS, {"corte": CORTE}).fetchall(),
                           columns=["id_cliente", "codigo", "id_cuenta", "monto_usd", "dia", "ts_ms",
                                    "nocturna", "tercero"])
        print(f"  PostgreSQL: {len(perfiles):,} perfiles y {len(ops):,} operaciones de 120 días "
              f"({time.perf_counter() - t0:.1f} s)")

    t0 = time.perf_counter()
    p = Lotes(r)
    for f in perfiles.itertuples():
        p.hset(clave(f.id_cliente, "perfil"), mapping={
            "tipo_cliente": f.tipo_cliente, "es_pep": int(f.es_pep), "antiguedad_dias": int(f.antiguedad_dias),
            "ratio_rechazo": "" if f.ratio_rechazo is None else float(f.ratio_rechazo),
            "ratio_cuentas_terceros": "" if f.ratio_cuentas_terceros is None else float(f.ratio_cuentas_terceros),
            "ratio_nocturno": float(f.ratio_nocturno), "ultima_operacion": f.ultima_operacion, "ult_offset": -1})

    ops["monto_usd"] = ops["monto_usd"].astype(float)
    ops["umbral"] = ops["monto_usd"].between(9000, 9999.995)
    diario = ops.groupby(["id_cliente", "dia"]).agg(n=("codigo", "size"), usd=("monto_usd", "sum"),
                                                    umbral=("umbral", "sum"), noct=("nocturna", "sum"),
                                                    terc=("tercero", "sum"))
    for (id_cli, dia), fila in diario.iterrows():
        p.hset(clave(id_cli, "diario"), mapping={
            f"n:{dia}": int(fila.n), f"usd:{dia}": round(float(fila.usd), 2), f"umbral:{dia}": int(fila.umbral),
            f"noct:{dia}": int(fila.noct), f"terc:{dia}": int(fila.terc)})

    corte_ms = int(CORTE.timestamp() * 1000)
    for fila in ops[ops.ts_ms >= corte_ms - 7 * 86_400_000].itertuples():
        p.zadd(clave(fila.id_cliente, "ops24h"), {f"{fila.codigo}|{fila.monto_usd:.2f}": fila.ts_ms})
    destinos = ops.groupby(["id_cliente", "id_cuenta"]).ts_ms.max()
    for (id_cli, id_cta), ts in destinos.items():
        p.zadd(clave(id_cli, "destinos"), {f"cta:{id_cta}": int(ts)})
    p.execute()
    print(f"  Redis: {r.dbsize():,} claves cargadas ({time.perf_counter() - t0:.1f} s), "
          f"memoria usada: {r.info('memory')['used_memory_human']}")
    return perfiles


def entrenar_modelo(perfiles):
    """Mismo modelo que el notebook de Databricks: mismas filas, orden, parámetros y semilla."""
    registros = [{f: None if v is None else float(v) for f, v in fila.items()}
                 for fila in perfiles[FEATURES_MODELO].to_dict("records")]
    X = np.array([vector(r) for r in registros])
    modelo = IsolationForest(n_estimators=300, max_samples=1024, contamination="auto", random_state=42).fit(X)
    scores = -modelo.score_samples(X)
    orden = np.sort(scores)[::-1]
    umbral_alto = orden[int(round(len(X) * 0.02)) - 1]   # top 2 % = riesgo ALTO (lo que revisa el back-office)
    umbral_medio = orden[int(round(len(X) * 0.10)) - 1]  # top 10 % = riesgo MEDIO
    p99 = dict(zip(FEATURES_MODELO, np.percentile(X, 99, axis=0)))
    MODELO.write_bytes(pickle.dumps({"modelo": modelo, "umbral_alto": umbral_alto,
                                     "umbral_medio": umbral_medio, "p99": p99}))
    print(f"  Isolation Forest entrenado con {len(X):,} clientes; umbrales de riesgo: "
          f"ALTO ≥ {umbral_alto:.3f} (top 2 %), MEDIO ≥ {umbral_medio:.3f} (top 10 %)")


if __name__ == "__main__":
    print("1 · Topics en Confluent Cloud");  crear_topics()
    print("2 · Carga de Redis desde PostgreSQL");  perfiles = cargar_redis()
    print("3 · Modelo");  entrenar_modelo(perfiles)
    print("Listo.")
