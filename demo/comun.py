"""
NexoCambio · Demo de la Parte 2: configuración y lógica compartida.

El reloj de la demo está congelado en la fecha de corte de la Parte 1 (22/10/2026 00:00, Lima):
las ventanas de 30 y 90 días son las mismas que usa v_features_cliente en PostgreSQL.

Claves en Redis (ver modelo_nosql.pdf): todas las de un cliente llevan el hash tag {id_cliente}.
    cli:{id}:perfil    Hash        features batch + ultima_operacion + ult_offset
    cli:{id}:diario    Hash        contadores por día: n:, usd:, umbral:, noct:, terc: + AAAAMMDD
    cli:{id}:ops24h    Sorted set  operaciones de los últimos 7 días (score = instante en ms)
    cli:{id}:destinos  Sorted set  cuentas destino (score = último uso en ms)
    op:{codigo}:riesgo Hash        score, nivel y motivos de una operación
    cola:riesgo        Sorted set  operaciones ordenadas por riesgo (cola del back-office)
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import redis

DEMO = Path(__file__).resolve().parent
RAIZ = DEMO.parent
LIMA = timezone(timedelta(hours=-5))
CORTE = datetime(2026, 10, 22, tzinfo=LIMA)
CORTE_MS = int(CORTE.timestamp() * 1000)
DIA_MS = 86_400_000

TOPIC_OPERACIONES = "nexocambio.operaciones"
TOPICS = {  # nombre: (particiones, compactado)
    "nexocambio.operaciones": (6, False),
    "nexocambio.comprobantes": (6, False),
    "nexocambio.estados": (6, False),
    "nexocambio.clientes": (3, True),
}
MODELO = DEMO / "_modelo.pkl"  # lo genera 0_preparar.py (no se versiona)

FEATURES = ["operaciones_30d", "monto_promedio_usd_90d", "dias_desde_ultima_operacion", "ratio_rechazo",
            "ratio_cerca_umbral_90d", "ratio_cuentas_terceros", "variacion_monto_30d", "ratio_nocturno"]
# El modelo usa solo las de comportamiento: con las de tamaño confundía a los clientes grandes con inusuales.
FEATURES_MODELO = ["ratio_rechazo", "ratio_cerca_umbral_90d", "ratio_cuentas_terceros",
                   "variacion_monto_30d", "ratio_nocturno"]


def clave(id_cliente, nombre):
    return f"cli:{{{id_cliente}}}:{nombre}"


# --- Conexiones ---------------------------------------------------------------

def _env():
    valores = {}
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def kafka_conf(**extra):
    env = _env()
    return {"bootstrap.servers": env["KAFKA_BOOTSTRAP"], "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN", "sasl.username": env["KAFKA_API_KEY"],
            "sasl.password": env["KAFKA_API_SECRET"], "log_level": 4, **extra}  # solo avisos y errores


def conectar_redis():
    return redis.Redis(host="localhost", port=6379, decode_responses=True)


def conectar_postgres():
    # La contraseña la toma libpq de %APPDATA%\postgresql\pgpass.conf.
    return psycopg.connect("host=localhost port=5433 dbname=nexocambio user=postgres",
                           options="-c search_path=nexocambio -c TimeZone=America/Lima", autocommit=True)


# --- Features desde Redis -----------------------------------------------------

# Días anteriores al corte: DIAS[0] = 21/10/2026 … DIAS[119] = 24/06/2026.
DIAS = [(CORTE - timedelta(days=d)).strftime("%Y%m%d") for d in range(1, 121)]

# Suma las ventanas dentro de Redis y devuelve solo los totales: un viaje de red con pocos datos.
LUA_LEER = """
-- KEYS: perfil, diario, ops24h, destinos · ARGV: corte_ms, dia_ms, 120 días (del más reciente al más antiguo)
local corte, dia = tonumber(ARGV[1]), tonumber(ARGV[2])
local function sumar(prefijo, desde, hasta)
  local campos = {}
  for i = desde, hasta do campos[#campos + 1] = prefijo .. ':' .. ARGV[i + 2] end
  local total = 0
  for _, v in ipairs(redis.call('HMGET', KEYS[2], unpack(campos))) do
    if v then total = total + tonumber(v) end
  end
  return tostring(total)
end
return {redis.call('HGETALL', KEYS[1]),
        sumar('n', 1, 30), sumar('n', 1, 90), sumar('n', 31, 120),
        sumar('usd', 1, 30), sumar('usd', 1, 90), sumar('usd', 31, 120), sumar('umbral', 1, 90),
        redis.call('ZCOUNT', KEYS[3], corte - dia, corte),
        redis.call('ZCOUNT', KEYS[4], corte - 30 * dia, corte)}
"""
_scripts = {}


def leer_features(r, id_cliente):
    """Lee el estado del cliente en un solo viaje a Redis y arma las features (mismas que v_features_cliente)."""
    script = _scripts.setdefault(id(r), r.register_script(LUA_LEER))
    claves = [clave(id_cliente, c) for c in ("perfil", "diario", "ops24h", "destinos")]
    plano, *sumas, ops24h, destinos30 = script(keys=claves, args=[CORTE_MS, DIA_MS, *DIAS])
    perfil = dict(zip(plano[::2], plano[1::2]))
    n30, n90, n_prev, usd30, usd90, usd_prev, umbral90 = map(float, sumas)
    num = lambda c: float(perfil[c]) if perfil.get(c) not in (None, "") else None

    return {
        "operaciones_30d": int(n30),
        "monto_promedio_usd_90d": round(usd90 / n90, 2) if n90 else None,
        "dias_desde_ultima_operacion": round((CORTE_MS - int(perfil["ultima_operacion"])) / DIA_MS),
        "ratio_rechazo": num("ratio_rechazo"),
        "ratio_cerca_umbral_90d": round(umbral90 / n90, 3) if n90 else None,
        "ratio_cuentas_terceros": num("ratio_cuentas_terceros"),
        "variacion_monto_30d": (round((usd30 / n30) / (usd_prev / n_prev), 2)
                                if n30 and n_prev and usd_prev else None),
        "ratio_nocturno": num("ratio_nocturno"),
        # Features que solo existen en línea (no están en PostgreSQL).
        "operaciones_24h": ops24h,
        "cuentas_destino_30d": destinos30,
    }


def vector(features):
    """Entrada del modelo, con las mismas reglas de nulos que el notebook de Databricks."""
    relleno = {"ratio_rechazo": 0, "variacion_monto_30d": 1}
    return [float(features[f]) if features[f] is not None and not (isinstance(features[f], float)
            and math.isnan(features[f])) else float(relleno.get(f, 0)) for f in FEATURES_MODELO]
