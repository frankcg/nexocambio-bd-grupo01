"""
NexoCambio · Generador de datos sintéticos.

Genera los CSV que carga sql/03_data.sql y la muestra datos/dataset.csv.
Solo usa la biblioteca estándar de Python y es reproducible (semilla fija).

    cd grupo_01
    python generador/generar_datos.py              # volumen completo (~50 mil clientes)
    python generador/generar_datos.py --escala 0.02 # prueba rápida

Reglas de negocio replicadas del backend de NexoCambio:
  · spread 0,45 % (casa) y 1,2 % (cripto); baja 40 % desde 5 000 USD (tasa preferencial)
  · tasa = (precio_usd origen / precio_usd destino) × (1 − spread); vigencia de 5 minutos
  · montos entre 10 y 1 000 000 USD; decimales por moneda
  · estados: Pendiente de comprobante → Pendiente de validación → En proceso → Procesada,
    con rechazos posibles desde Pendiente de validación y En proceso

Los IDs no van en los CSV: las tablas usan GENERATED ALWAYS AS IDENTITY y COPY los asigna
en el orden de las filas (1, 2, 3…). El generador usa esa misma numeración para las FK.
"""
import argparse
import bisect
import csv
import itertools
import math
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # carpeta grupo_01
SALIDA = RAIZ / "datos" / "completo"
MUESTRA = RAIZ / "datos" / "dataset.csv"

LIMA = timezone(timedelta(hours=-5))  # Perú no usa horario de verano
INICIO = datetime(2025, 1, 1, tzinfo=LIMA)
FIN = datetime(2026, 10, 22, tzinfo=LIMA)  # exclusivo: datos hasta el 21/10/2026
DIAS = (FIN - INICIO).days
PASO_TASAS = 5  # minutos entre tasas de referencia
BUCKETS = DIAS * 24 * 60 // PASO_TASAS

CLIENTES_BASE = 50_000
COTIZACIONES_CLIENTE_BASE = 1_500_000  # + ~25 % anónimas ≈ 2 millones
CONVERSION_CLIENTE, CONVERSION_ANONIMA = 0.55, 0.15

# --------------------------------------------------------------- catálogos
# Deben coincidir con los INSERT de 03_data.sql (los IDs son el orden de inserción).
DECIMALES = {"PEN": 2, "USD": 2, "EUR": 2, "USDT": 2, "USDC": 2, "BTC": 6, "ETH": 5}
CRIPTO = ("USDT", "USDC", "BTC", "ETH")
BANCOS = [(1, 35), (2, 25), (3, 20), (4, 12), (5, 4), (6, 4)]  # (id_banco, peso)
REDES_MONEDA = {"USDT": [(1, 70), (2, 30)], "USDC": [(2, 60), (3, 40)], "BTC": [(4, 1)], "ETH": [(2, 1)]}
ANALISTAS = list(range(1, 11))  # id_usuario 1..10 analistas, 11..12 supervisores
SUPERVISORES = [11, 12]
SPREAD = {"casa": Decimal("0.0045"), "cripto": Decimal("0.012")}
FACTOR_PREFERENCIAL = Decimal("0.6")
PREFERENCIAL_DESDE_USD = 5000

PARES_CASA = [(("USD", "PEN"), 45), (("PEN", "USD"), 43), (("EUR", "PEN"), 3), (("PEN", "EUR"), 4),
              (("USD", "EUR"), 3), (("EUR", "USD"), 2)]
PARES_CRIPTO = [(("PEN", "USDT"), 22), (("USD", "USDT"), 13), (("USDT", "PEN"), 12), (("USDT", "USD"), 6),
                (("USD", "BTC"), 10), (("PEN", "BTC"), 6), (("BTC", "USD"), 6), (("BTC", "PEN"), 3),
                (("USD", "ETH"), 7), (("ETH", "USD"), 5), (("PEN", "USDC"), 5), (("USDC", "PEN"), 5)]

HORAS = [0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.4, 1, 2.5, 4, 5, 5, 4, 3.5, 4, 4.5, 4.5, 4, 3, 2, 1.5, 1, 0.7, 0.4]
FACTOR_DIA = [1.0, 1.0, 1.0, 1.0, 1.05, 0.5, 0.3]  # lunes … domingo

NOMBRES = ["José", "Luis", "Carlos", "Juan", "Miguel", "Jorge", "Pedro", "Diego", "Renzo", "Bruno", "Andrés",
           "Ricardo", "Fernando", "Gustavo", "Martín", "Sebastián", "Alonso", "Raúl", "Víctor", "César",
           "María", "Rosa", "Ana", "Lucía", "Carmen", "Sofía", "Valeria", "Camila", "Andrea", "Paola",
           "Daniela", "Fiorella", "Milagros", "Patricia", "Gabriela", "Claudia", "Mónica", "Ximena", "Elena", "Diana"]
APELLIDOS = ["Quispe", "Flores", "Sánchez", "Rodríguez", "García", "Rojas", "Mendoza", "Díaz", "Torres",
             "Ramírez", "Chávez", "Vargas", "Castillo", "Huamán", "Mamani", "Gutiérrez", "Espinoza", "Ruiz",
             "Vásquez", "Castro", "Romero", "Ramos", "Morales", "Fernández", "Salazar", "Cruz", "Herrera",
             "Paredes", "Medina", "Aguilar", "Silva", "Córdova", "Ríos", "Palacios", "Cáceres", "Zapata",
             "León", "Navarro", "Ponce", "Valdivia"]
EMPRESA_RAIZ = ["Inversiones", "Comercial", "Distribuidora", "Corporación", "Importaciones", "Servicios",
                "Grupo", "Industrias", "Constructora", "Agroexportadora", "Consultora", "Textil", "Tecnologías"]
EMPRESA_NOMBRE = ["Andina", "del Pacífico", "Los Olivos", "Santa Rosa", "Inca", "Miraflores", "San Martín",
                  "Huascarán", "Amazonas", "Costa Verde", "Sol Naciente", "Chavín", "Titicaca", "Pachacútec",
                  "Nazca", "Paracas", "Machu Picchu", "Rímac", "La Molina", "Surco", "Callao", "Arequipa",
                  "Cusco", "Trujillo", "Piura", "Chiclayo", "Ica", "Tacna", "Puno", "Junín"]
EMPRESA_SOCIEDAD = ["S.A.C.", "S.A.", "E.I.R.L.", "S.R.L."]
OCUPACIONES = [("Dependiente", 45), ("Independiente", 22), ("Empresario", 12), ("Estudiante", 6),
               ("Jubilado", 5), ("Otro", 3), ("", 7)]
ACTIVIDADES = [("Comercio", 32), ("Servicios", 25), ("Manufactura", 12), ("Tecnología", 10),
               ("Construcción", 11), ("Otro", 10)]
CARGOS = ["Gerente General", "Apoderado", "Gerente de Finanzas", "Director", "Gerente Comercial"]
DOMINIOS = [("gmail.com", 55), ("hotmail.com", 20), ("outlook.com", 15), ("yahoo.com", 6), ("icloud.com", 4)]
ARCHIVOS = [("image/jpeg", "jpg", 45), ("image/png", "png", 25), ("application/pdf", "pdf", 25),
            ("image/webp", "webp", 5)]
RECHAZO_VALIDACION = ["El monto transferido no coincide con la operación",
                      "El comprobante es ilegible o está incompleto",
                      "No se recibió la transferencia en la cuenta de NexoCambio",
                      "La cuenta de origen pertenece a un tercero"]
RECHAZO_PROCESO = ["Los datos de la cuenta de destino son inválidos",
                   "Alerta de cumplimiento: operación inusual (UIF)"]
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def elegir(rnd, opciones):
    """opciones = [(valor, peso), ...]"""
    valores, pesos = zip(*opciones)
    return rnd.choices(valores, weights=pesos)[0]


def ts(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S-05")


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def cuantizar(valor: Decimal, decimales: int) -> Decimal:
    return valor.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


class Escritor:
    """CSV con cabecera; '' = NULL para COPY ... (FORMAT csv)."""

    def __init__(self, nombre, columnas):
        self.f = open(SALIDA / f"{nombre}.csv", "w", newline="", encoding="utf-8")
        self.w = csv.writer(self.f, lineterminator="\n")
        self.w.writerow(columnas)
        self.filas = 0

    def fila(self, *valores):
        self.w.writerow(valores)
        self.filas += 1
        return self.filas  # = id asignado por IDENTITY

    def cerrar(self):
        self.f.close()


# ------------------------------------------------------- tasas de referencia
def generar_tasas(rnd):
    """Precio en USD de cada moneda cada 5 minutos (series con reversión a la media y GBM)."""
    dt = PASO_TASAS / 1440
    sq = math.sqrt(dt)
    precios = {m: [0.0] * BUCKETS for m in ("PEN", "EUR", "USDT", "USDC", "BTC", "ETH")}
    pen, eur, btc, eth = 3.72, 1.035, 94_000.0, 3_350.0
    for i in range(BUCKETS):
        t = i / BUCKETS
        # Soles por dólar: el sol se aprecia de ~3,72 a ~3,40 (reversión lenta a la tendencia).
        pen += 0.05 * ((3.72 - 0.32 * t) - pen) * dt + 0.003 * pen * sq * rnd.gauss(0, 1)
        # Dólares por euro: sube de ~1,04 a ~1,17 durante 2025 y luego se estabiliza.
        eur += 0.05 * ((1.035 + 0.135 * min(1.0, t * 1.8)) - eur) * dt + 0.004 * eur * sq * rnd.gauss(0, 1)
        z1, z2 = rnd.gauss(0, 1), rnd.gauss(0, 1)
        btc *= math.exp(0.02 * math.log(95_000 / btc) * dt - 0.5 * 0.028 ** 2 * dt + 0.028 * sq * z1)
        eth *= math.exp(0.02 * math.log(3_000 / eth) * dt - 0.5 * 0.038 ** 2 * dt
                        + 0.038 * sq * (0.8 * z1 + 0.6 * z2))
        precios["PEN"][i] = 1 / pen
        precios["EUR"][i] = eur
        precios["USDT"][i] = 1 + max(-0.003, min(0.003, rnd.gauss(0, 0.0004)))
        precios["USDC"][i] = 1 + max(-0.003, min(0.003, rnd.gauss(0, 0.0003)))
        precios["BTC"][i] = btc
        precios["ETH"][i] = eth

    w = Escritor("tasa_referencial", ["codigo_moneda", "fecha_hora", "precio_usd", "fuente"])
    fuente = {"PEN": "open.er-api.com", "EUR": "open.er-api.com"}
    for i in range(BUCKETS):
        t = ts(INICIO + timedelta(minutes=i * PASO_TASAS))
        for m, serie in precios.items():
            w.fila(m, t, f"{serie[i]:.8f}", fuente.get(m, "coingecko.com"))
    w.cerrar()
    return precios, w.filas


# ------------------------------------------------------------------ clientes
class Cliente:
    __slots__ = ("id", "codigo", "tipo", "registro", "dia_registro", "ultimo_dia", "peso", "perfil",
                 "nombre", "pico", "cuentas")


def generar_clientes(rnd, n):
    codigos, correos, docs = set(), set(), set()

    def unico(conjunto, fabrica):
        while True:
            v = fabrica()
            if v not in conjunto:
                conjunto.add(v)
                return v

    def hora_registro(dia):
        h = rnd.choices(range(24), weights=HORAS)[0]
        return INICIO + timedelta(days=dia, hours=h, minutes=rnd.randrange(60), seconds=rnd.randrange(60))

    clientes = []
    for _ in range(n):
        c = Cliente()
        c.tipo = "empresa" if rnd.random() < 0.15 else "persona"
        if rnd.random() < 0.06:  # clientes del piloto, registrados en diciembre de 2024
            dia = -rnd.randint(1, 30)
        else:  # registros crecientes en el tiempo: densidad ∝ (0,4 + t)
            u = rnd.random()
            dia = int((-0.4 + math.sqrt(0.16 + 1.8 * u)) * (DIAS - 1))
        c.registro = hora_registro(dia)
        c.dia_registro = dia
        # 25 % se registra y nunca opera; el resto tiene actividad con cola pesada.
        c.peso = 0.0 if rnd.random() < 0.25 else min(60.0, rnd.paretovariate(1.6))
        if c.tipo == "empresa":
            c.peso *= 1.8
        c.ultimo_dia = dia + int(rnd.expovariate(1 / 450))  # abandono
        c.perfil, c.pico, c.cuentas = "normal", None, {}
        clientes.append(c)

    # Perfiles anómalos (Parte 2: detección de operaciones inusuales).
    activos = [c for c in clientes if c.peso > 0 and c.tipo == "persona"]
    for perfil, proporcion in (("pitufeo", 0.005), ("pico", 0.004), ("nocturno", 0.003), ("multicuenta", 0.004)):
        for c in rnd.sample(activos, max(1, int(len(activos) * proporcion))):
            if c.perfil != "normal":
                continue
            c.perfil = perfil
            if perfil == "pitufeo":
                c.peso, c.ultimo_dia = max(c.peso, 4.0) * 3, DIAS
            elif perfil == "pico":
                inicio = rnd.randint(max(0, c.dia_registro + 30), DIAS - 1) if c.dia_registro + 30 < DIAS else DIAS - 1
                c.pico, c.ultimo_dia, c.peso = (inicio, inicio + 3), max(c.ultimo_dia, inicio + 3), max(c.peso, 2.0)

    clientes.sort(key=lambda c: c.registro)  # IDs en orden de registro

    w_cli = Escritor("cliente", ["codigo_cliente", "tipo_cliente", "tipo_documento", "numero_documento", "correo",
                                 "telefono", "password_hash", "fecha_registro"])
    w_per = Escritor("persona_natural", ["id_cliente", "nombres", "apellidos", "fecha_nacimiento", "ocupacion",
                                         "es_pep"])
    w_emp = Escritor("empresa", ["id_cliente", "razon_social", "actividad"])
    w_rep = Escritor("representante_legal", ["id_cliente", "nombre", "tipo_documento", "numero_documento", "cargo",
                                             "vigente", "fecha_registro"])
    alfanum = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    for c in clientes:
        c.codigo = unico(codigos, lambda: "CLI-" + "".join(rnd.choices(alfanum, k=6)))
        tel = "9" + "".join(rnd.choices("0123456789", k=8))
        pw = "pbkdf2_sha256$600000$" + "".join(rnd.choices("0123456789abcdef", k=48))
        if c.tipo == "persona":
            nombres = rnd.choice(NOMBRES) + (" " + rnd.choice(NOMBRES) if rnd.random() < 0.4 else "")
            apellidos = f"{rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
            c.nombre = f"{nombres} {apellidos}"
            tipo_doc = elegir(rnd, [("DNI", 94), ("CE", 4), ("Pasaporte", 2)])
            largo = {"DNI": 8, "CE": 9, "Pasaporte": 9}[tipo_doc]
            doc = unico(docs, lambda: (tipo_doc, "".join(rnd.choices("0123456789", k=largo))))[1]
            base = sin_tildes(f"{nombres.split()[0]}.{apellidos.split()[0]}").lower()
            correo = unico(correos, lambda: f"{base}{rnd.randint(1, 9999)}@{elegir(rnd, DOMINIOS)}")
            cid = w_cli.fila(c.codigo, "persona", tipo_doc, doc, correo, tel, pw, ts(c.registro))
            edad = rnd.triangular(18.5, 75, 34)
            nacimiento = (c.registro - timedelta(days=int(edad * 365.25))).date()
            pep = c.perfil == "nocturno" and rnd.random() < 0.5 or rnd.random() < 0.015
            w_per.fila(cid, nombres, apellidos, nacimiento.isoformat(), elegir(rnd, OCUPACIONES), "t" if pep else "f")
        else:
            c.nombre = f"{rnd.choice(EMPRESA_RAIZ)} {rnd.choice(EMPRESA_NOMBRE)} {rnd.choice(EMPRESA_SOCIEDAD)}"
            ruc = unico(docs, lambda: ("RUC", "20" + "".join(rnd.choices("0123456789", k=9))))[1]
            slug = sin_tildes(c.nombre.split()[1]).lower().replace(".", "")
            correo = unico(correos, lambda: f"finanzas.{slug}{rnd.randint(1, 99999)}@empresa.com.pe")
            cid = w_cli.fila(c.codigo, "empresa", "RUC", ruc, correo, tel, pw, ts(c.registro))
            w_emp.fila(cid, c.nombre, elegir(rnd, ACTIVIDADES))
            dnis = rnd.sample(range(10_000_000, 99_999_999), 2)
            if rnd.random() < 0.2:  # representante anterior, ya no vigente
                w_rep.fila(cid, f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}", "DNI",
                           str(dnis[1]), rnd.choice(CARGOS), "f", ts(c.registro))
            w_rep.fila(cid, f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}", "DNI",
                       str(dnis[0]), rnd.choice(CARGOS), "t", ts(c.registro))
        c.id = cid
    for w in (w_cli, w_per, w_emp, w_rep):
        w.cerrar()

    with open(SALIDA / "etiquetas_anomalias.csv", "w", newline="", encoding="utf-8") as f:
        e = csv.writer(f, lineterminator="\n")
        e.writerow(["codigo_cliente", "perfil"])
        for c in clientes:
            if c.perfil != "normal":
                e.writerow([c.codigo, c.perfil])
    return clientes, {"cliente": w_cli.filas, "persona_natural": w_per.filas, "empresa": w_emp.filas,
                      "representante_legal": w_rep.filas}


# ------------------------------------------------------ cotizaciones y operaciones
class Simulador:
    def __init__(self, rnd, clientes, precios, escala):
        self.rnd, self.clientes, self.precios = rnd, clientes, precios
        self.dias_registro = [c.dia_registro for c in clientes]
        self.acumulado = list(itertools.accumulate(c.peso for c in clientes))
        self.codigos_op = set()
        self.w_cta = Escritor("cuenta_cliente", ["id_cliente", "codigo_moneda", "tipo", "id_banco", "tipo_cuenta",
                                                 "numero_cuenta", "titular", "id_red", "direccion_wallet",
                                                 "fecha_registro"])
        self.w_cot = Escritor("cotizacion", ["id_cliente", "modalidad", "moneda_origen", "moneda_destino",
                                             "monto_origen", "tasa", "monto_destino", "spread_aplicado",
                                             "tasa_preferencial", "fuente_tasas", "fecha_cotizacion",
                                             "fecha_expiracion"])
        self.w_op = Escritor("operacion", ["codigo_operacion", "id_cotizacion", "id_cliente", "id_cuenta_origen",
                                           "id_cuenta_destino", "estado_actual", "numero_transferencia",
                                           "motivo_rechazo", "fecha_operacion", "fecha_actualizacion"])
        self.w_com = Escritor("comprobante", ["id_operacion", "nombre_archivo", "content_type", "tamano_bytes",
                                              "ruta_s3", "fecha_subida"])
        self.w_his = Escritor("historial_estado", ["id_operacion", "estado_anterior", "estado_nuevo", "id_usuario",
                                                   "comentario", "fecha_cambio"])
        self.muestra = open(MUESTRA, "w", newline="", encoding="utf-8")
        self.w_mue = csv.writer(self.muestra, lineterminator="\n")
        self.w_mue.writerow(["codigo_operacion", "fecha_operacion", "codigo_cliente", "tipo_cliente", "modalidad",
                             "moneda_origen", "moneda_destino", "monto_origen", "monto_destino", "tasa",
                             "monto_usd", "tasa_preferencial", "estado_actual", "minutos_validacion"])
        # Tasa diaria de cotizaciones por unidad de "peso activo", calibrada al volumen objetivo.
        activo = [0.0] * (DIAS + 2)
        for c in clientes:
            if c.peso > 0:
                activo[max(0, c.dia_registro + 1)] += c.peso
                activo[min(DIAS + 1, max(0, c.ultimo_dia + 1))] -= c.peso
        self.peso_activo = list(itertools.accumulate(activo))[:DIAS]
        esperado = sum(FACTOR_DIA[(INICIO + timedelta(days=d)).weekday()] * self.peso_activo[d] for d in range(DIAS))
        self.lambda_ = COTIZACIONES_CLIENTE_BASE * escala / esperado
        self.velocidad = {u: self.rnd.uniform(0.6, 1.6) for u in ANALISTAS}  # factor de demora por analista

    # .................................................................. apoyo
    def precio(self, moneda, t):
        if moneda == "USD":
            return 1.0
        i = min(BUCKETS - 1, int((t - INICIO).total_seconds() // (PASO_TASAS * 60)))
        return self.precios[moneda][i]

    def elegir_cliente(self, dia):
        k = bisect.bisect_right(self.dias_registro, dia - 1)  # registrados hasta el día anterior
        if k == 0 or self.acumulado[k - 1] == 0:
            return None
        total = self.acumulado[k - 1]
        for _ in range(40):
            c = self.clientes[bisect.bisect_right(self.acumulado, self.rnd.random() * total, 0, k)]
            if c.ultimo_dia >= dia:
                return c
        return None

    def monto_usd(self, c, modalidad, t, dia):
        r = self.rnd
        if c is not None and c.perfil == "pitufeo" and r.random() < 0.8:
            return r.uniform(9_000, 9_990)  # fraccionamiento bajo el umbral de US$ 10 000
        if c is not None and c.tipo == "empresa":
            usd = r.lognormvariate(math.log(4_000), 1.0)
        else:
            usd = r.lognormvariate(math.log(450 if modalidad == "casa" else 250), 0.95)
        if c is not None and c.pico and c.pico[0] <= dia <= c.pico[1]:
            usd *= r.uniform(12, 25)
        if c is not None and c.perfil == "nocturno":
            usd *= r.uniform(3, 8)
        return max(10.5, min(990_000.0, usd))

    def momento(self, dia, c):
        r = self.rnd
        if c is not None and c.perfil == "nocturno" and r.random() < 0.7:
            hora = r.randint(0, 4)
        else:
            hora = r.choices(range(24), weights=HORAS)[0]
        return INICIO + timedelta(days=dia, hours=hora, minutes=r.randrange(60), seconds=r.randrange(60))

    def cuenta(self, c, moneda, t):
        """Devuelve el id de una cuenta del cliente en esa moneda (la crea si hace falta)."""
        r = self.rnd
        existentes = c.cuentas.setdefault(moneda, [])
        nueva = not existentes or r.random() < (0.7 if c.perfil == "multicuenta" else 0.04)
        if not nueva:
            return r.choice(existentes)
        if moneda in CRIPTO:
            red = elegir(r, REDES_MONEDA[moneda])
            if red == 1:
                direccion = "T" + "".join(r.choices(BASE58, k=33))
            elif red == 2:
                direccion = "0x" + "".join(r.choices("0123456789abcdef", k=40))
            elif red == 3:
                direccion = "".join(r.choices(BASE58, k=44))
            else:
                direccion = "bc1q" + "".join(r.choices("023456789acdefghjklmnpqrstuvwxyz", k=38))
            cid = self.w_cta.fila(c.id, moneda, "wallet", "", "", "", "", red, direccion, ts(t))
        else:
            # multicuenta: cuentas de terceros (titular distinto al cliente)
            titular = (f"{r.choice(NOMBRES)} {r.choice(APELLIDOS)} {r.choice(APELLIDOS)}"
                       if c.perfil == "multicuenta" and existentes else c.nombre)
            tipo_cuenta = "Corriente" if c.tipo == "empresa" else elegir(r, [("Ahorros", 85), ("Corriente", 15)])
            numero = "".join(r.choices("0123456789", k=r.choice((13, 14, 20))))
            cid = self.w_cta.fila(c.id, moneda, "banco", elegir(r, BANCOS), tipo_cuenta, numero, titular,
                                  "", "", ts(t))
        existentes.append(cid)
        return cid

    @staticmethod
    def horario_atencion(t):
        """El back-office atiende de lunes a sábado de 08:00 a 20:00."""
        if t.hour >= 20:
            t = (t + timedelta(days=1)).replace(hour=8, minute=0, second=0)
        elif t.hour < 8:
            t = t.replace(hour=8, minute=0, second=0)
        if t.weekday() == 6:
            t = (t + timedelta(days=1)).replace(hour=8, minute=0, second=0)
        return t

    # ............................................................ simulación
    def ejecutar(self):
        r = self.rnd
        for dia in range(DIAS):
            fecha = INICIO + timedelta(days=dia)
            media = self.lambda_ * FACTOR_DIA[fecha.weekday()] * self.peso_activo[dia]
            n = max(0, round(r.gauss(media, math.sqrt(media)))) if media > 0 else 0
            eventos = []
            for _ in range(n):
                c = self.elegir_cliente(dia)
                if c is not None:
                    eventos.append((self.momento(dia, c), c, True))
            for _ in range(round(n / 3)):  # visitantes que cotizan sin iniciar sesión
                eventos.append((self.momento(dia, None), None, False))
            eventos.sort(key=lambda e: e[0])  # IDs en orden cronológico
            for t, c, con_sesion in eventos:
                self.cotizar(t, c, con_sesion, dia)
        for w in (self.w_cta, self.w_cot, self.w_op, self.w_com, self.w_his):
            w.cerrar()
        self.muestra.close()

    def cotizar(self, t, c, con_sesion, dia):
        r = self.rnd
        cripto = r.random() < (0.05 if c is not None and c.tipo == "empresa" else 0.22)
        modalidad = "cripto" if cripto else "casa"
        origen, destino = elegir(r, PARES_CRIPTO if cripto else PARES_CASA)
        usd = self.monto_usd(c, modalidad, t, dia)
        p_o, p_d = self.precio(origen, t), self.precio(destino, t)
        monto_origen = cuantizar(Decimal(repr(usd / p_o)), DECIMALES[origen])
        monto_usd = float(monto_origen) * p_o
        preferencial = monto_usd >= PREFERENCIAL_DESDE_USD
        spread = SPREAD[modalidad] * (FACTOR_PREFERENCIAL if preferencial else 1)
        tasa = cuantizar(Decimal(repr(p_o / p_d)) * (1 - spread), 10)
        monto_destino = cuantizar(monto_origen * tasa, DECIMALES[destino])
        fuente = elegir(r, [("en_vivo", 970), ("cache", 25), ("referencial", 5)])
        id_cot = self.w_cot.fila(c.id if con_sesion else "", modalidad, origen, destino, monto_origen, tasa,
                                 monto_destino, f"{spread:.5f}", "t" if preferencial else "f", fuente, ts(t),
                                 ts(t + timedelta(minutes=5)))

        if con_sesion:
            convierte = r.random() < (0.95 if c.perfil == "pitufeo" else CONVERSION_CLIENTE)
        else:
            convierte = r.random() < CONVERSION_ANONIMA
            c = self.elegir_cliente(dia) if convierte else None  # el visitante inicia sesión y opera
        if not convierte or c is None:
            return
        f_op = t + timedelta(seconds=r.uniform(15, 240))
        if f_op >= FIN:
            return
        self.operar(id_cot, c, origen, destino, f_op, modalidad, monto_origen, monto_destino, tasa, monto_usd,
                    preferencial)

    def operar(self, id_cot, c, origen, destino, f_op, modalidad, monto_origen, monto_destino, tasa, monto_usd,
               preferencial):
        r = self.rnd
        cta_o, cta_d = self.cuenta(c, origen, f_op), self.cuenta(c, destino, f_op)
        while True:
            codigo = "NX-" + "".join(r.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
            if codigo not in self.codigos_op:
                self.codigos_op.add(codigo)
                break
        # Transiciones: (estado, fecha, usuario, comentario). Se cortan en la fecha de corte.
        hitos = [("Pendiente de comprobante", f_op, None, None)]
        comprobantes, nro_transferencia, motivo, min_validacion = [], "", "", ""
        if r.random() >= 0.05:  # 5 % abandona sin subir el comprobante
            subida = f_op + timedelta(minutes=r.lognormvariate(math.log(9), 0.8))
            comprobantes.append(subida)
            hitos.append(("Pendiente de validación", subida, None, None))
            if r.random() < 0.8:
                nro_transferencia = "".join(r.choices("0123456789", k=r.randint(8, 12)))
            rechazo_val = r.random() < (0.10 if c.perfil == "multicuenta" else 0.04)
            usuario = r.choice(ANALISTAS)
            decision = self.horario_atencion(subida) + timedelta(
                minutes=r.lognormvariate(math.log(18), 0.7) * self.velocidad[usuario])
            if r.random() < 0.1:  # el cliente reemplaza el comprobante antes de la revisión
                comprobantes.append(subida + (decision - subida) * r.uniform(0.1, 0.9))
            min_validacion = round((decision - subida).total_seconds() / 60, 1)
            if rechazo_val:
                motivo = r.choice(RECHAZO_VALIDACION)
                hitos.append(("Rechazada", decision, usuario, motivo))
            else:
                hitos.append(("En proceso", decision, usuario, None))
                cumplimiento = c.perfil != "normal" and r.random() < 0.15
                if cumplimiento or r.random() < 0.04:
                    motivo = RECHAZO_PROCESO[1] if cumplimiento else r.choice(RECHAZO_PROCESO)
                    hitos.append(("Rechazada", decision + timedelta(minutes=r.uniform(5, 120)),
                                  r.choice(SUPERVISORES) if cumplimiento else usuario, motivo))
                else:
                    hitos.append(("Procesada", decision + timedelta(minutes=r.lognormvariate(math.log(25), 0.6)),
                                  usuario, None))
        hitos = [h for h in hitos if h[1] < FIN]
        comprobantes = [s for s in comprobantes if s < FIN]
        estado = hitos[-1][0]
        if estado != "Rechazada":
            motivo = ""
        if estado == "Pendiente de comprobante":
            nro_transferencia = ""
        if len(hitos) < 3:
            min_validacion = ""

        id_op = self.w_op.fila(codigo, id_cot, c.id, cta_o, cta_d, estado, nro_transferencia, motivo, ts(f_op),
                               ts(hitos[-1][1]))
        anterior = ""
        for estado_h, fecha, usuario, comentario in hitos:
            self.w_his.fila(id_op, anterior, estado_h, usuario or "", comentario or "", ts(fecha))
            anterior = estado_h
        for k, subida in enumerate(comprobantes, 1):
            tipo, ext = elegir(r, [((ct, e), p) for ct, e, p in ARCHIVOS])
            nombre = r.choice(["voucher", "constancia", "comprobante", "captura", f"IMG_{subida:%Y%m%d}"]) + "." + ext
            tamano = r.randint(40_000, 900_000) if ext == "pdf" else r.randint(120_000, 3_800_000)
            ruta = f"s3://nexo-prod-comprobantes/comprobantes/{c.codigo}/{codigo}/{k}_{nombre}"
            self.w_com.fila(id_op, nombre, tipo, tamano, ruta, ts(subida))
        if id_op % 90 == 0:  # ~1 % de las operaciones va a la muestra dataset.csv
            self.w_mue.writerow([codigo, ts(f_op), c.codigo, c.tipo, modalidad, origen, destino, monto_origen,
                                 monto_destino, tasa, f"{monto_usd:.2f}", "t" if preferencial else "f", estado,
                                 min_validacion])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--escala", type=float, default=1.0, help="fracción del volumen completo (1.0 ≈ 50 mil clientes)")
    p.add_argument("--semilla", type=int, default=2026)
    a = p.parse_args()
    rnd = random.Random(a.semilla)
    SALIDA.mkdir(parents=True, exist_ok=True)

    inicio = datetime.now()
    precios, n_tasas = generar_tasas(rnd)
    print(f"tasa_referencial     {n_tasas:>10,}")
    clientes, filas = generar_clientes(rnd, max(100, int(CLIENTES_BASE * a.escala)))
    for tabla, n in filas.items():
        print(f"{tabla:<20} {n:>10,}")
    sim = Simulador(rnd, clientes, precios, a.escala)
    sim.ejecutar()
    for w in (sim.w_cta, sim.w_cot, sim.w_op, sim.w_com, sim.w_his):
        print(f"{Path(w.f.name).stem:<20} {w.filas:>10,}")
    print(f"Listo en {(datetime.now() - inicio).seconds} s. CSV en {SALIDA}")


if __name__ == "__main__":
    main()
