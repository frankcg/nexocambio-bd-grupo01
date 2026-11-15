"""
NexoCambio · Demo, paso 1: las mismas features, en PostgreSQL y en Redis.

Para cada cliente calcula las features con v_features_cliente (PostgreSQL) y las lee de Redis,
comprueba que coinciden y compara los tiempos (mediana, después de una lectura de calentamiento
que abre la conexión y carga el script Lua). Por defecto compara un cliente típico con el de
más historial.

    .venv\\Scripts\\python demo/1_comparar.py [CLI-06EZN7 CLI-ZYCHEZ]
"""
import statistics
import sys
import time

from comun import FEATURES, conectar_postgres, conectar_redis, leer_features


def cronometrar(funcion, veces):
    funcion()  # calentamiento
    tiempos, resultado = [], None
    for _ in range(veces):
        t0 = time.perf_counter()
        resultado = funcion()
        tiempos.append((time.perf_counter() - t0) * 1000)
    return resultado, statistics.median(tiempos)


def mostrar(v):
    return "—" if v is None else f"{v:,.3f}".rstrip("0").rstrip(".")


def comparar(pg, r, codigo):
    id_cliente, n_ops = pg.execute("""SELECT c.id_cliente, count(o.*) FROM cliente c
                                      LEFT JOIN operacion o USING (id_cliente)
                                      WHERE c.codigo_cliente = %s GROUP BY 1""", (codigo,)).fetchone()
    fila_pg, ms_pg = cronometrar(lambda: pg.execute(
        f"SELECT {', '.join(FEATURES)} FROM v_features_cliente WHERE id_cliente = %s", (id_cliente,)).fetchone(), 5)
    feat_redis, ms_redis = cronometrar(lambda: leer_features(r, id_cliente), 50)

    print(f"\nCliente {codigo} · {n_ops:,} operaciones en su historial")
    print(f"  {'feature':<32}{'PostgreSQL':>12}{'Redis':>12}")
    iguales = True
    for nombre, valor_pg in zip(FEATURES, fila_pg):
        valor_pg, valor_r = None if valor_pg is None else float(valor_pg), feat_redis[nombre]
        ok = (valor_pg is None) == (valor_r is None) and (valor_pg is None or abs(valor_pg - valor_r) < 1e-6)
        iguales &= ok
        print(f"  {nombre:<32}{mostrar(valor_pg):>12}{mostrar(valor_r):>12}{'' if ok else '  ≠'}")
    print(f"  {'operaciones_24h (solo en línea)':<32}{'—':>12}{feat_redis['operaciones_24h']:>12}")
    print(f"  {'cuentas_destino_30d (en línea)':<32}{'—':>12}{feat_redis['cuentas_destino_30d']:>12}")
    print(f"  ¿Mismas features? {'Sí' if iguales else 'NO'}")
    return codigo, n_ops, ms_pg, ms_redis


codigos = sys.argv[1:] or ["CLI-06EZN7", "CLI-ZYCHEZ"]
r = conectar_redis()
with conectar_postgres() as pg:
    resultados = [comparar(pg, r, c) for c in codigos]

print(f"\n  {'cliente':<12}{'operaciones':>12}{'PostgreSQL':>14}{'Redis':>12}")
for codigo, n_ops, ms_pg, ms_redis in resultados:
    print(f"  {codigo:<12}{n_ops:>12,}{ms_pg:>11.1f} ms{ms_redis:>9.1f} ms")
print("\n  PostgreSQL agrega todo el historial: su tiempo crece con las operaciones del cliente.")
print("  Redis suma contadores ya calculados: su tiempo es el mismo para cualquier cliente.\n")
