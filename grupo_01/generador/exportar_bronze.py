"""
NexoCambio · Exporta los extractos de PostgreSQL que forman la capa bronze del medallion (Parte 2).

Escribe en datos/bronze/ (no se versiona; ~25 MB comprimido):
    operaciones.csv.gz   las 918 479 operaciones, con su cotización y el monto en USD (v_operacion)
    clientes.csv.gz      los 50 000 clientes, con su nombre y si son PEP
    cuentas.csv.gz       las cuentas destino, con su titular
    etiquetas.csv.gz     las anomalías inyectadas por el generador (solo para evaluar el modelo)

Las fechas van en UTC con formato ISO 8601. También imprime sumas de control de v_features_cliente
para comprobar que el notebook de Databricks calcula exactamente las mismas features.

Se ejecuta desde grupo_01/ (requiere psycopg):
    python generador/exportar_bronze.py
"""
import gzip
import shutil
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "datos" / "bronze"
UTC = "to_char({c} AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"')"

EXTRACTOS = {
    "operaciones": f"""
        SELECT id_operacion, codigo_operacion, id_cliente, estado_actual,
               {UTC.format(c='fecha_operacion')} AS fecha_operacion_utc, id_cuenta_destino, id_cotizacion,
               modalidad, moneda_origen, moneda_destino, monto_origen, monto_usd, spread_aplicado,
               tasa_preferencial, motivo_rechazo
        FROM v_operacion ORDER BY id_operacion""",
    "clientes": f"""
        SELECT c.id_cliente, c.codigo_cliente, c.tipo_cliente,
               {UTC.format(c='c.fecha_registro')} AS fecha_registro_utc,
               coalesce(p.nombres || ' ' || p.apellidos, e.razon_social) AS nombre,
               coalesce(p.es_pep, false) AS es_pep
        FROM cliente c
        LEFT JOIN persona_natural p USING (id_cliente)
        LEFT JOIN empresa e USING (id_cliente)
        ORDER BY c.id_cliente""",
    "cuentas": """
        SELECT id_cuenta, id_cliente, tipo, id_banco, titular FROM cuenta_cliente ORDER BY id_cuenta""",
}

FEATURES = ["operaciones_30d", "monto_promedio_usd_90d", "dias_desde_ultima_operacion", "ratio_rechazo",
            "ratio_cerca_umbral_90d", "ratio_cuentas_terceros", "variacion_monto_30d", "ratio_nocturno"]


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    with psycopg.connect("host=localhost port=5433 dbname=nexocambio user=postgres",
                         options="-c search_path=nexocambio -c TimeZone=America/Lima") as pg:
        for nombre, sql in EXTRACTOS.items():
            archivo = DESTINO / f"{nombre}.csv.gz"
            filas = 0
            with gzip.open(archivo, "wb") as gz, pg.cursor().copy(
                    f"COPY ({sql}) TO STDOUT WITH (FORMAT csv, HEADER true)") as copia:
                for bloque in copia:
                    gz.write(bloque)
                    filas += bytes(bloque).count(b"\n")
            print(f"  {archivo.name:<22}{filas - 1:>10,} filas  {archivo.stat().st_size / 2**20:6.1f} MB")

        etiquetas = RAIZ / "datos" / "completo" / "etiquetas_anomalias.csv"
        with open(etiquetas, "rb") as origen, gzip.open(DESTINO / "etiquetas.csv.gz", "wb") as gz:
            shutil.copyfileobj(origen, gz)
        print(f"  {'etiquetas.csv.gz':<22}{sum(1 for _ in open(etiquetas, encoding='utf-8')) - 1:>10,} filas")

        print("\nSumas de control de v_features_cliente (PostgreSQL):")
        sumas = ", ".join(f"count({f}), round(sum({f})::numeric, 3)" for f in FEATURES)
        fila = pg.execute(f"SELECT count(*), {sumas} FROM v_features_cliente").fetchone()
        print(f"  clientes: {fila[0]:,}")
        for i, f in enumerate(FEATURES):
            print(f"  {f:<30} no nulos {fila[1 + 2 * i]:>7,}   suma {fila[2 + 2 * i]:>18,}")


if __name__ == "__main__":
    main()
