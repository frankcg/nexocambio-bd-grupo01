"""
NexoCambio · Genera la presentación final sobre la plantilla oficial de UTEC Posgrado.

    python generador/presentacion/construir.py "<plantilla UTEC .pptx>" grupo_01/presentacion/NexoCambio_presentacion_final.pptx

Usa los diseños de la plantilla (portada, fondo oscuro y fondo claro, con logo y lema) y quita sus
diapositivas de ejemplo. Cada diapositiva lleva notas del orador con lo que hay que decir.
"""
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

DIR = Path(__file__).parent
PLANTILLA, SALIDA = sys.argv[1], sys.argv[2]
IC = DIR / "recursos"  # íconos y bombilla de la plantilla UTEC; arquitectura.png recortado de arquitectura.pdf

OSCURO, CIAN, CLARO = RGBColor(0x4D, 0x4B, 0x4C), RGBColor(0x00, 0xE1, 0xFF), RGBColor(0xEE, 0xEE, 0xEE)
BLANCO, TARJETA_OSC = RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0x5E, 0x5C, 0x5D)
TENUE_OSC, TENUE_CLA, GRIS = RGBColor(0xCF, 0xCF, 0xCF), RGBColor(0x6E, 0x6C, 0x6D), RGBColor(0xA6, 0xA6, 0xA6)
FUENTE = "Space Grotesk"

prs = Presentation(PLANTILLA)
L_PORTADA, L_OSCURO, L_CLARO = prs.slide_layouts[2], prs.slide_layouts[3], prs.slide_layouts[4]

# Se quitan las 17 diapositivas de ejemplo; se conservan los diseños (fondos, logo, lema).
for sld in list(prs.slides._sldIdLst):
    prs.part.drop_rel(sld.rId)
    prs.slides._sldIdLst.remove(sld)


# --- Utilidades ----------------------------------------------------------------

def nueva(layout):
    s = prs.slides.add_slide(layout)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


def sin_cortes(t):
    """Espacios no separables en cifras: «US$ 10 000», «16 %» o «20 ms» nunca se parten en dos líneas."""
    t = re.sub(r"(?<=\d) (?=\d{3}\b)", "\u00a0", t)
    t = re.sub(r"(US\$|≈|\+US\$|N\.º) ", "\\1\u00a0", t)
    return re.sub(r"(?<=\d) (?=(%|ms|s|M|mil)\b)", "\u00a0", t)


def texto(s, x, y, w, h, parrafos, size=13, color=OSCURO, bold=False, align=PP_ALIGN.LEFT,
          anchor=MSO_ANCHOR.TOP, espacio=0, nombre=None, font=FUENTE):
    """parrafos: str o lista; cada párrafo es str o lista de (texto, {opciones})."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if nombre:
        tb.name = nombre
    tf = tb.text_frame
    tf.word_wrap, tf.vertical_anchor = True, anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, par in enumerate(parrafos if isinstance(parrafos, list) else [parrafos]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(espacio)
        for t, o in (par if isinstance(par, list) else [(par, {})]):
            r = p.add_run()
            r.text = sin_cortes(t)
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.color.rgb = o.get("color", color)
    return tb


def caja(s, x, y, w, h, fill, redondeada=True, linea=None):
    forma = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if redondeada else MSO_SHAPE.RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    if redondeada:
        forma.adjustments[0] = 0.08
    forma.fill.solid()
    forma.fill.fore_color.rgb = fill
    if linea:
        forma.line.color.rgb = linea
        forma.line.width = Pt(1)
    else:
        forma.line.fill.background()
    forma.shadow.inherit = False
    return forma


def circulo(s, x, y, d, fill, numero, color_txt=OSCURO, size=14):
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = fill
    c.line.fill.background()
    c.shadow.inherit = False
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = str(numero)
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FUENTE, Pt(size), True, color_txt


def icono(s, archivo, x, y, lado):
    s.shapes.add_picture(str(IC / archivo), Inches(x), Inches(y), Inches(lado), Inches(lado))


def flecha(s, x, y, w, h, color):
    f = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(x), Inches(y), Inches(w), Inches(h))
    f.fill.solid()
    f.fill.fore_color.rgb = color
    f.line.fill.background()
    f.shadow.inherit = False


def marco(s, n, oscuro, titulo, subtitulo=None, notas=""):
    """Título, subtítulo y número de diapositiva (el logo y la mira vienen del diseño de la plantilla)."""
    texto(s, 9.27, 5.13, 0.6, 0.3, str(n), size=11, color=CIAN if oscuro else OSCURO, bold=True,
          align=PP_ALIGN.CENTER, nombre="Número")
    texto(s, 0.6, 1.0, 8.4, 0.5, titulo, size=24, bold=True, color=CIAN if oscuro else OSCURO, nombre="Título")
    if subtitulo:
        texto(s, 0.6, 1.5, 8.4, 0.4, subtitulo, size=12.5, color=TENUE_OSC if oscuro else TENUE_CLA, nombre="Subtítulo")
    s.notes_slide.notes_text_frame.text = notas


def estilo_grafico(chart, color_txt):
    chart.font.name, chart.font.size, chart.font.color.rgb = FUENTE, Pt(11), color_txt
    ca, va = chart.category_axis, chart.value_axis
    va.visible = False
    va.has_major_gridlines = False
    ca.format.line.fill.background()
    ca.tick_labels.font.color.rgb = color_txt
    ca.tick_labels.font.size = Pt(11)
    ca.tick_labels.font.name = FUENTE


# --- 1 · Portada -----------------------------------------------------------------
s = nueva(L_PORTADA)
caja(s, 0.70, 1.45, 2.1, 0.42, CIAN, redondeada=False)
texto(s, 0.70, 1.45, 2.1, 0.42, "BASE DE DATOS", size=15, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
texto(s, 0.62, 2.0, 6.5, 0.9, "NexoCambio", size=50, color=BLANCO)
texto(s, 0.62, 2.95, 5.9, 0.95, "Datos que protegen y hacen crecer el negocio", size=26, color=CIAN)
texto(s, 0.62, 4.35, 6.5, 0.6, [
    [("Grupo 1 · ", {"bold": True}), ("Frank Laura · Josue Campos · Mauricio Vallejos", {})],
    [("Docente: Luis Chicoma · Maestría, UTEC Posgrado · Lima, noviembre de 2026", {"size": 11, "color": TENUE_OSC})],
], size=12.5, color=BLANCO, espacio=3)
s.notes_slide.notes_text_frame.text = (
    "Presenta (sugerido): Frank.\n"
    "Somos el Grupo 1. Nuestro caso es NexoCambio, una casa de cambio digital de divisas y criptoactivos. "
    "La idea que vamos a defender: con un buen modelo de datos y la tecnología adecuada para cada problema, "
    "los mismos datos protegen al negocio del lavado de activos y además lo hacen crecer.")

# --- 2 · Empresa y contexto ------------------------------------------------------
s = nueva(L_OSCURO)
marco(s, 2, True, "Una casa de cambio digital que crece rápido",
      "Cambia divisas (PEN, USD, EUR) y criptoactivos (USDT, USDC, BTC, ETH) por web. Gana con el spread.",
      "Presenta (sugerido): Josue.\n"
      "NexoCambio compra y vende divisas y criptoactivos por una aplicación web. Su ingreso es el spread: la "
      "diferencia entre la tasa de mercado y la que ofrece al cliente (0,45 % en casa de cambio, 1,2 % en cripto; "
      "desde US$ 5 000 hay tasa preferencial). Atiende a personas y empresas, y un back-office valida cada operación. "
      "El negocio creció 9,3 veces en operaciones diarias en 20 meses. Los datos son ficticios, generados para el "
      "curso con autorización del docente, pero siguen las reglas reales del negocio.")
tarjetas = [("people_c.png", "50 000", "clientes, personas y empresas"),
            ("doc_c.png", "918 mil", "operaciones en 21 meses"),
            ("bars_c.png", "US$ 155 M", "de volumen en septiembre de 2026"),
            ("growth_c.png", "9,3×", "más operaciones diarias que en enero de 2025")]
for i, (ic, num, lab) in enumerate(tarjetas):
    x = 0.6 + i * 2.15
    caja(s, x, 2.15, 1.95, 1.95, TARJETA_OSC)
    icono(s, ic, x + 0.2, 2.3, 0.5)
    texto(s, x + 0.2, 2.9, 1.7, 0.5, num, size=21, bold=True, color=CIAN)
    texto(s, x + 0.2, 3.42, 1.6, 0.6, lab, size=11.5, color=BLANCO)
texto(s, 0.6, 4.4, 8.2, 0.35, [[("Ingreso por spread: ", {"bold": True, "color": BLANCO}),
                               ("US$ 594 mil en septiembre de 2026 · datos ficticios autorizados por el docente", {})]],
      size=11.5, color=TENUE_OSC)

# --- 3 · Proceso y problema ------------------------------------------------------
s = nueva(L_CLARO)
marco(s, 3, False, "El proceso: de la cotización a la decisión",
      "Cada operación pasa por cinco pasos; en dos de ellos el negocio pierde.",
      "Presenta (sugerido): Josue.\n"
      "El proceso que modelamos es la operación de cambio de punta a punta. El cliente cotiza y recibe una tasa "
      "garantizada por 5 minutos, registra la operación con sus cuentas, sube el comprobante de transferencia y el "
      "back-office la valida. Hay dos problemas de negocio. Uno de riesgo: el back-office revisa en orden de llegada "
      "y la UIF exige detectar lavado, que justamente se disfraza de operaciones normales. Otro de ingresos: menos "
      "de la mitad de las cotizaciones termina en operación. El resto de la presentación responde a esos dos problemas.")
pasos = [("Cotiza", "tasa garantizada por 5 minutos"), ("Registra", "cuentas de origen y destino"),
         ("Comprobante", "sube la transferencia"), ("Valida", "analistas y supervisores"),
         ("Decide", "procesada o rechazada")]
for i, (t, d) in enumerate(pasos):
    x = 0.6 + i * 1.74
    caja(s, x, 1.95, 1.5, 1.2, BLANCO)
    circulo(s, x + 0.12, 2.07, 0.34, CIAN, i + 1, size=12)
    texto(s, x + 0.12, 2.47, 1.3, 0.25, t, size=12, bold=True)
    texto(s, x + 0.12, 2.73, 1.3, 0.4, d, size=9.5, color=TENUE_CLA)
    if i < 4:
        flecha(s, x + 1.54, 2.43, 0.16, 0.24, GRIS)
problemas = [("eye_n.png", "Riesgo regulatorio",
              "El back-office revisa en orden de llegada y la UIF exige detectar el lavado, "
              "que se disfraza de operaciones justo bajo US$ 10 000."),
             ("calc_n.png", "Ventas que se pierden",
              "Solo el 46 % de las cotizaciones termina en operación (15 % entre visitantes). Una tasa que vence es "
              "una venta perdida.")]
for i, (ic, t, d) in enumerate(problemas):
    x = 0.6 + i * 4.35
    caja(s, x, 3.4, 4.1, 1.45, BLANCO)
    icono(s, ic, x + 0.2, 3.6, 0.65)
    texto(s, x + 1.05, 3.55, 2.85, 0.35, t, size=14, bold=True)
    texto(s, x + 1.05, 3.92, 2.85, 0.85, d, size=11, color=TENUE_CLA)

# --- 4 · Modelo ER y decisiones --------------------------------------------------
s = nueva(L_CLARO)
marco(s, 4, False, "Modelo de datos: 15 entidades en 3FN",
      "Diseñado desde las reglas del negocio en PostgreSQL; el detalle completo está en modelo_ER.pdf.",
      "Presenta (sugerido): Josue.\n"
      "El modelo tiene 15 entidades en 3FN, agrupadas en cuatro dominios: clientes, cuentas y catálogos, precio y "
      "operación. Lo importante son las decisiones que protegen al negocio. La base, no solo la aplicación, hace "
      "cumplir las reglas: una máquina de estados con CHECK impide que una operación procesada vuelva atrás, y las "
      "FK compuestas obligan a que las cuentas sean del cliente que opera. Hay dos desnormalizaciones justificadas: "
      "la tasa queda guardada en la cotización porque es un contrato con el cliente, y el estado actual se guarda "
      "junto al historial para que la cola del back-office sea rápida sin perder la auditoría. Se probaron 29 casos "
      "inválidos y la base rechazó todos.")
dominios = [("Clientes", ["cliente", "persona_natural", "empresa", "representante_legal"]),
            ("Cuentas y catálogos", ["cuenta_cliente", "banco", "moneda", "red_blockchain", "moneda_red"]),
            ("Precio", ["tasa_referencial", "cotizacion"]),
            ("Operación", ["operacion", "comprobante", "historial_estado", "usuario_backoffice"])]
for i, (t, ents) in enumerate(dominios):
    x, y = 0.6 + (i % 2) * 2.45, 1.95 + (i // 2) * 1.5
    caja(s, x, y, 2.3, 1.38, BLANCO)
    texto(s, x + 0.15, y + 0.1, 2.0, 0.3, t, size=13, bold=True)
    texto(s, x + 0.15, y + 0.42, 2.05, 0.9, ents, size=9, color=TENUE_CLA, font="Consolas")
decisiones = [("La base hace cumplir las reglas", "Máquina de estados con CHECK: lo procesado no vuelve atrás"),
              ("Las cuentas son del cliente", "FK compuestas entre operación, cuenta y cliente"),
              ("La cotización es un contrato", "Tasa y monto guardados: una corrección no altera el pasado"),
              ("Cola rápida y auditable", "estado_actual junto al historial completo de estados")]
texto(s, 5.65, 2.0, 3.5, 0.3, "Decisiones que protegen al negocio", size=13, bold=True)
for i, (t, d) in enumerate(decisiones):
    y = 2.4 + i * 0.62
    circulo(s, 5.65, y + 0.02, 0.32, CIAN, i + 1, size=11)
    texto(s, 6.1, y, 3.0, 0.28, t, size=11.5, bold=True)
    texto(s, 6.1, y + 0.26, 3.0, 0.3, d, size=9.5, color=TENUE_CLA)

# --- 5 · Consultas e insights ----------------------------------------------------
s = nueva(L_OSCURO)
marco(s, 5, True, "Lo que dicen los datos: tres hallazgos",
      "10 consultas SQL, de básicas a avanzadas. Estas tres cambian decisiones.",
      "Presenta (sugerido): Mauricio.\n"
      "De las 10 consultas, tres cambian decisiones. C6, con DENSE_RANK por mes: el cliente número uno en volumen "
      "julio, agosto y setiembre es CLI-ZYCHEZ, y el 75 % de sus operaciones está justo debajo de US$ 10 000, el "
      "umbral de registro ante la UIF: fracciona. C2: la tasa de rechazo es casi igual en los seis bancos y el motivo "
      "que domina es la alerta de cumplimiento, así que el problema es el comportamiento del cliente, no el banco. "
      "C7, con ROLLUP: solo el 46 % de las cotizaciones se convierte; los visitantes, 15 %. Los dos primeros "
      "hallazgos llevan al caso de IA; el tercero, a la oportunidad de ingresos.")
hallazgos = [("N.º 1", "El mejor cliente es el más riesgoso",
              "CLI-ZYCHEZ lidera el volumen en jul, ago y set (US$ 2,2 M en septiembre), y el 75 % de sus "
              "operaciones está justo debajo de US$ 10 000.", "C6 · CTE + DENSE_RANK"),
             ("8,5–8,8 %", "El rechazo no depende del banco",
              "Es casi igual en los 6 bancos. Domina la alerta de cumplimiento: el problema es el comportamiento "
              "del cliente.", "C2 · JOIN + FILTER"),
             ("46 %", "Más de la mitad de las cotizaciones se pierde",
              "Con sesión convierte 56 %; un visitante, 15 %. Una vez creada la operación, 87 % termina procesada.",
              "C7 · CASE + ROLLUP")]
for i, (num, t, d, tag) in enumerate(hallazgos):
    x = 0.6 + i * 2.9
    caja(s, x, 2.05, 2.7, 2.75, TARJETA_OSC)
    texto(s, x + 0.2, 2.2, 2.3, 0.55, num, size=28, bold=True, color=CIAN)
    texto(s, x + 0.2, 2.8, 2.35, 0.55, t, size=13, bold=True, color=BLANCO)
    texto(s, x + 0.2, 3.38, 2.33, 1.05, d, size=10.5, color=TENUE_OSC)
    texto(s, x + 0.2, 4.47, 2.3, 0.25, tag, size=9, color=CIAN, font="Consolas")

# --- 6 · Features --------------------------------------------------------------------
s = nueva(L_CLARO)
marco(s, 6, False, "Features: cada cliente en 8 números",
      "8 variables calculadas con SQL para cada cliente; CLI-ZYCHEZ frente a un cliente típico.",
      "Presenta (sugerido): Mauricio.\n"
      "Construimos 8 features por cliente con SQL, en la vista v_features_cliente. Comparen a CLI-ZYCHEZ con un "
      "cliente típico: 405 operaciones en 30 días frente a 6, y el 75 % cerca del umbral frente a cero. Pero ninguna "
      "feature sola detecta todo: cada perfil inusual se ve en una distinta (fraccionamiento, cuentas de terceros, "
      "actividad nocturna). Por eso hace falta un modelo multivariable. Una lección importante: al principio el "
      "modelo usaba las 8, y las de tamaño hacían que confundiera a los clientes grandes legítimos con sospechosos. "
      "Ahora usa solo las 5 de comportamiento: juzga cómo opera el cliente, no cuánto opera.")
filas = [("operaciones_30d", "Actividad del último mes", "405", "6", False),
         ("monto_promedio_usd_90d", "Ticket promedio", "7 315", "830", False),
         ("dias_desde_ultima_operacion", "Recencia", "0", "7", False),
         ("ratio_cerca_umbral_90d", "Montos bajo el umbral", "0,754", "0,000", True),
         ("ratio_rechazo", "Historial de rechazos", "0,220", "0,120", True),
         ("ratio_cuentas_terceros", "Cuentas de otros titulares", "0,000", "0,000", True),
         ("variacion_monto_30d", "Cambio brusco de ticket", "1,03", "1,15", True),
         ("ratio_nocturno", "Operaciones de 0 a 5 a. m.", "0,010", "0,000", True)]
tabla = s.shapes.add_table(len(filas) + 1, 4, Inches(0.6), Inches(1.95), Inches(5.9), Inches(2.9)).table
for j, w in enumerate((2.25, 2.05, 0.8, 0.8)):
    tabla.columns[j].width = Inches(w)
cab = ["Feature", "Qué mide", "ZYCHEZ", "Típico"]
for i in range(len(filas) + 1):
    tabla.rows[i].height = Inches(0.32)
    for j in range(4):
        c = tabla.cell(i, j)
        c.margin_left = c.margin_right = Inches(0.08)
        c.margin_top = c.margin_bottom = Inches(0.02)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.fill.solid()
        if i == 0:
            c.fill.fore_color.rgb, val, col, b = OSCURO, cab[j], BLANCO, True
        else:
            f = filas[i - 1]
            c.fill.fore_color.rgb = BLANCO if f[4] else CLARO
            val = [f[0], f[1], f[2], f[3]][j]
            col, b = OSCURO, (j == 2 and f[0] in ("operaciones_30d", "ratio_cerca_umbral_90d"))
        p = c.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT if j >= 2 else PP_ALIGN.LEFT
        r = p.add_run()
        r.text = val
        r.font.name = "Consolas" if (j == 0 and i > 0) else FUENTE
        r.font.size, r.font.bold, r.font.color.rgb = Pt(9.5 if j == 0 else 10.5), b, col
texto(s, 0.6, 4.92, 5.9, 0.25, "Filas en blanco: las 5 features de comportamiento que usa el modelo.",
      size=9.5, color=TENUE_CLA)
caja(s, 6.8, 1.95, 2.45, 2.85, OSCURO)
icono(s, "brain_c.png", 7.0, 2.1, 0.55)
texto(s, 7.0, 2.75, 2.1, 0.6, "Cómo opera, no cuánto opera", size=14, bold=True, color=CIAN)
texto(s, 7.0, 3.4, 2.1, 1.35, "Con las features de tamaño, el modelo marcaba a 59 de los 94 clientes grandes "
      "legítimos. Con las 5 de comportamiento: a ninguno, y encuentra más casos.", size=10.5, color=BLANCO)

# --- 7 · Optimización ------------------------------------------------------------------
s = nueva(L_OSCURO)
marco(s, 7, True, "Optimización: respuestas al instante",
      "EXPLAIN y EXPLAIN ANALYZE antes y después; tiempos en milisegundos (mediana de 5 corridas).",
      "Presenta (sugerido): Mauricio.\n"
      "Elegimos tres consultas que el negocio usa todo el tiempo y las medimos con EXPLAIN ANALYZE. O1, el historial "
      "de un cliente: PostgreSQL no indexa las FK solas, así que leía toda la tabla; con un índice compuesto (cliente, "
      "fecha descendente) baja de 171 a 0,4 ms y entrega las filas ya ordenadas. O2, la cola del back-office: solo 217 "
      "de 918 mil operaciones están abiertas, así que un índice parcial con solo esas filas la deja en 0,4 ms aunque el "
      "histórico crezca. O3, el embudo mensual: el índice solo no bastaba; leer el plan mostró que el cuello estaba en "
      "otra tabla, y con BRIN más una reescritura bajó de 485 a 177 ms. No basta con crear índices: hay que leer el plan.")
datos = CategoryChartData()
datos.categories = ["O3 · Embudo mensual", "O2 · Cola del back-office", "O1 · Historial del cliente"]
datos.add_series("Antes", (485, 263, 171))
datos.add_series("Después", (177, 0.4, 0.4))
g = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.95), Inches(4.9), Inches(2.95), datos).chart
estilo_grafico(g, BLANCO)
g.has_legend, g.legend.include_in_layout = True, False
g.legend.font.color.rgb, g.legend.font.size = BLANCO, Pt(10)
plot = g.plots[0]
plot.gap_width, plot.overlap = 60, -10
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format, dl.number_format_is_linked = '[<1]"0,4";0', False  # 0,4 ms con coma decimal; el resto, entero
dl.font.name = FUENTE
dl.position, dl.font.size, dl.font.color.rgb = XL_LABEL_POSITION.OUTSIDE_END, Pt(10), BLANCO
for serie, color in zip(plot.series, (GRIS, CIAN)):
    serie.format.fill.solid()
    serie.format.fill.fore_color.rgb = color
tecnicas = [("O1", "Índice compuesto (cliente, fecha)", "171 → 0,4 ms: la pantalla «Mis operaciones» al instante"),
            ("O2", "Índice parcial: solo las 217 abiertas", "263 → 0,4 ms: la cola no se vuelve lenta con los años"),
            ("O3", "BRIN + reescritura de la consulta", "485 → 177 ms: el reporte mensual 2,7 veces más rápido")]
for i, (tag, t, d) in enumerate(tecnicas):
    y = 2.0 + i * 0.92
    caja(s, 5.65, y, 3.6, 0.8, TARJETA_OSC)
    texto(s, 5.8, y + 0.1, 0.5, 0.3, tag, size=13, bold=True, color=CIAN)
    texto(s, 6.3, y + 0.08, 2.85, 0.3, t, size=11, bold=True, color=BLANCO)
    texto(s, 6.3, y + 0.38, 2.85, 0.4, d, size=9.5, color=TENUE_OSC)

# --- 8 · Caso de IA ------------------------------------------------------------------------
s = nueva(L_CLARO)
marco(s, 8, False, "Caso de IA: a quién debe revisar cumplimiento",
      "Isolation Forest no supervisado, entrenado en Databricks y versionado en MLflow.",
      "Presenta (sugerido): Frank.\n"
      "El caso de IA es detectar operaciones inusuales para prevenir el lavado de activos. Entrenamos un Isolation "
      "Forest, que aprende sin que nadie le diga qué es fraude: lo raro se aísla con pocos cortes. Lo evaluamos con "
      "las anomalías que inyectamos en los datos. Si el back-office revisa solo el 2 % de clientes con mayor score, "
      "encuentra el 69 % de los casos inusuales: 34 veces más que revisando al azar, y sin marcar a ningún cliente "
      "grande legítimo. Detecta casi todo el fraccionamiento y la actividad nocturna; los picos de monto no se ven "
      "en batch, y por eso el scoring también corre en tiempo real. El dato más fuerte para la gerencia: 1 de cada 6 "
      "dólares que mueve NexoCambio viene de clientes de riesgo alto. El modelo prioriza; la decisión es humana.")
stats = [("69 %", "de los casos inusuales, revisando el 2 % de clientes"),
         ("34×", "más efectivo que revisar al azar"),
         ("0 de 94", "clientes grandes legítimos marcados")]
for i, (num, lab) in enumerate(stats):
    x = 0.6 + i * 1.75
    caja(s, x, 1.95, 1.6, 1.3, BLANCO)
    texto(s, x + 0.15, 2.05, 1.35, 0.5, num, size=24, bold=True)
    texto(s, x + 0.15, 2.58, 1.33, 0.65, lab, size=9.5, color=TENUE_CLA)
datos = CategoryChartData()
datos.categories = ["Pico de monto", "Multicuenta", "Actividad nocturna", "Fraccionamiento"]
datos.add_series("Detectados", (0.049, 0.731, 0.945, 1.0))
g = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(3.4), Inches(5.0), Inches(1.6), datos).chart
estilo_grafico(g, OSCURO)
g.has_legend = False
g.has_title = True
g.chart_title.text_frame.text = "Casos detectados por tipo de comportamiento"
tp = g.chart_title.text_frame.paragraphs[0].runs[0].font
tp.size, tp.bold, tp.name, tp.color.rgb = Pt(10), True, FUENTE, OSCURO
plot = g.plots[0]
plot.gap_width = 45
plot.has_data_labels = True
plot.data_labels.number_format, plot.data_labels.number_format_is_linked = "0%", False
plot.data_labels.position, plot.data_labels.font.size = XL_LABEL_POSITION.OUTSIDE_END, Pt(10)
plot.data_labels.font.name = FUENTE
plot.series[0].format.fill.solid()
plot.series[0].format.fill.fore_color.rgb = OSCURO
g.value_axis.maximum_scale = 1.15
caja(s, 5.95, 1.95, 3.3, 2.95, OSCURO)
texto(s, 6.15, 2.1, 2.9, 0.3, "Exposición del negocio · 90 días", size=10.5, color=TENUE_OSC)
texto(s, 6.15, 2.4, 2.95, 0.95, "1 de cada 6 dólares", size=24, bold=True, color=CIAN)
texto(s, 6.15, 3.35, 2.9, 1.45, [
    "viene de 438 clientes de riesgo ALTO: 16,9 % del volumen (US$ 75 M) y 16,2 % del spread.",
    [("Incluye a los dos mayores clientes del negocio.", {"bold": True})]], size=10.5, color=BLANCO, espacio=4)

# --- 9 · Arquitectura --------------------------------------------------------------------
s = nueva(L_CLARO)
marco(s, 9, False, "Arquitectura: cada tecnología en lo que hace mejor",
      "Polyglot Persistence: cada pieza resuelve un patrón de acceso distinto.",
      "Presenta (sugerido): Frank.\n"
      "No reemplazamos PostgreSQL: lo complementamos. Polyglot Persistence es usar la tecnología adecuada para cada "
      "patrón de acceso. PostgreSQL sigue siendo el sistema de registro, con integridad y transacciones. Cada cambio "
      "viaja como evento por Kafka en Confluent Cloud. Un procesador mantiene en Redis el perfil de cada cliente, y "
      "el scoring lo lee en milisegundos: calcular las mismas features en PostgreSQL toma de 6 a más de 100 ms y crece "
      "con el historial; en Redis toma lo mismo para cualquier cliente. Databricks recibe el histórico con una "
      "arquitectura medallion (bronze, silver, gold), entrena el modelo y lo versiona en MLflow, con un Job programado "
      "cada noche. Las features son idénticas en PostgreSQL, Redis y Databricks: lo verificamos.")
s.shapes.add_picture(str(IC / "arquitectura.png"), Inches(1.2), Inches(1.9), Inches(7.1))

# --- 10 · Valor de negocio ----------------------------------------------------------------
s = nueva(L_OSCURO)
marco(s, 10, True, "Una plataforma que protege y hace crecer",
      "Los mismos datos, las mismas features y el mismo modelo responden tres preguntas.",
      "Presenta (sugerido): Frank.\n"
      "Esta es la diapositiva más importante para el negocio. Primero, proteger: a quién revisar. El 16 % del spread "
      "viene de clientes de riesgo alto, y ahora cumplimiento revisa 438 clientes en vez de 35 mil. Segundo, rescatar: "
      "cada día unos 1 200 clientes registrados cotizan y no operan en 24 horas; en 90 días eso suma US$ 864 mil de "
      "spread no cobrado, la mitad de lo que se cobró. Cuando vence la tasa, el sistema dispara una oferta en tiempo "
      "real. Tercero, reactivar: 4 991 clientes frecuentes se están enfriando y valían US$ 145 mil al mes; Databricks "
      "entrega la lista cada semana. Y una regla común: a un cliente de riesgo alto no se le ofrece ningún incentivo. "
      "Los montos de recuperación son escenarios (10 % y 20 %) sobre datos ficticios.")
valor = [("target_c.png", "PROTEGER", "¿A quién revisar?", "16 %", "del spread viene de clientes de riesgo ALTO",
          "438 clientes en vez de 35 438 · en tiempo real"),
         ("energy_c.png", "RESCATAR", "¿A quién recuperar ahora?", "US$ 864 mil", "de spread en cotizaciones abandonadas (90 días)",
          "Oferta al vencer la tasa · +US$ 29 mil/mes si vuelve el 10 %"),
         ("people_c.png", "REACTIVAR", "¿A quién llamar esta semana?", "4 991", "clientes que se enfrían; valían US$ 145 mil/mes",
          "Lista gold en Databricks · +US$ 29 mil/mes si vuelve el 20 %")]
for i, (ic, tag, q, num, lab, det) in enumerate(valor):
    x = 0.6 + i * 2.9
    caja(s, x, 2.0, 2.7, 2.65, TARJETA_OSC)
    icono(s, ic, x + 0.2, 2.15, 0.48)
    texto(s, x + 0.8, 2.2, 1.8, 0.25, tag, size=10, bold=True, color=CIAN)
    texto(s, x + 0.8, 2.43, 1.85, 0.3, q, size=10.5, color=BLANCO)
    texto(s, x + 0.2, 2.85, 2.4, 0.5, num, size=24, bold=True, color=CIAN)
    texto(s, x + 0.2, 3.35, 2.35, 0.5, lab, size=10.5, bold=True, color=BLANCO)
    texto(s, x + 0.2, 3.9, 2.35, 0.65, det, size=9.5, color=TENUE_OSC)
texto(s, 0.6, 4.82, 8.2, 0.3, [[("Regla común: ", {"bold": True, "color": CIAN}),
                                ("a un cliente de riesgo ALTO no se le ofrece ningún incentivo. "
                                 "Escenarios sobre datos ficticios.", {})]], size=10.5, color=TENUE_OSC)

# --- 11 · Demo ---------------------------------------------------------------------------------
s = nueva(L_CLARO)
marco(s, 11, False, "Demo: un mismo evento, dos destinos",
      "En vivo, siguiendo a CLI-ZYCHEZ: de PostgreSQL al tiempo real y al Data Lake.",
      "Presenta (sugerido): Frank, con Josue y Mauricio en las terminales.\n"
      "Guía completa en demo/README.md. 1) En PostgreSQL: la base rechaza una transición inválida; C6 y las features "
      "delatan a CLI-ZYCHEZ; el índice baja la consulta de unos 70 a 0,6 ms. 2) Publicamos una operación de "
      "CLI-ZYCHEZ en Kafka: el procesador actualiza Redis y el modelo la marca como riesgo alto en unos 20 ms. "
      "3) Dos cotizaciones que vencen: el cliente típico recibe una oferta; CLI-ZYCHEZ, ninguna. 4) El Job de "
      "Databricks lleva los mismos eventos a Delta Lake. Lanzar la ingesta al empezar el paso 2: tarda unos 45 s.")
demo = [("PostgreSQL", "Rechaza una transición inválida; C6 y las features delatan a CLI-ZYCHEZ; un índice: 72 → 0,6 ms"),
        ("Tiempo real", "Una operación de CLI-ZYCHEZ viaja por Kafka; Redis y el modelo la marcan riesgo ALTO"),
        ("Cotización abandonada", "Al vencer la tasa: oferta al cliente típico, ninguna a CLI-ZYCHEZ"),
        ("Data Lake", "El Job de Databricks lleva los mismos eventos a Delta Lake")]
for i, (t, d) in enumerate(demo):
    x, y = 0.6 + (i % 2) * 3.0, 1.95 + (i // 2) * 1.45
    caja(s, x, y, 2.8, 1.3, BLANCO)
    circulo(s, x + 0.15, y + 0.15, 0.36, CIAN, i + 1, size=12)
    texto(s, x + 0.65, y + 0.17, 2.05, 0.3, t, size=12.5, bold=True)
    texto(s, x + 0.15, y + 0.6, 2.5, 0.65, d, size=10, color=TENUE_CLA)
caja(s, 6.8, 1.95, 2.45, 2.75, OSCURO)
texto(s, 7.0, 2.1, 2.1, 0.3, "Tiempos medidos", size=12, bold=True, color=CIAN)
for i, (num, lab) in enumerate([("≈ 1 s", "Kafka, ida y vuelta a la nube"), ("≈ 2 ms", "Redis: leer y actualizar"),
                                ("≈ 20 ms", "Modelo: score y motivos")]):
    texto(s, 7.0, 2.5 + i * 0.7, 2.1, 0.35, num, size=17, bold=True, color=BLANCO)
    texto(s, 7.0, 2.85 + i * 0.7, 2.1, 0.3, lab, size=9.5, color=TENUE_OSC)

# --- 12 · Conclusiones -----------------------------------------------------------------------
s = nueva(L_OSCURO)
s.shapes.add_picture(str(IC / "bombilla.png"), Inches(6.75), Inches(1.15), Inches(3.1), Inches(3.1))
texto(s, 9.27, 5.13, 0.6, 0.3, "12", size=11, color=CIAN, bold=True, align=PP_ALIGN.CENTER)
caja(s, -0.12, 1.0, 4.0, 0.75, CIAN, redondeada=False)
texto(s, 0.6, 1.0, 3.2, 0.75, "Conclusiones", size=28, bold=True, anchor=MSO_ANCHOR.MIDDLE)
conclusiones = [("Los datos cambian la lectura del negocio", "El mejor cliente era el más riesgoso."),
                ("PostgreSQL es la fuente de verdad", "Reglas en el modelo y consultas en menos de 1 ms con índices."),
                ("El reto era la latencia, no el volumen", "Kafka y Redis deciden en milisegundos; Databricks aprende."),
                ("Proteger y crecer con la misma plataforma", "1 de cada 6 dólares bajo control y ≈ US$ 58 mil/mes por recuperar.")]
for i, (t, d) in enumerate(conclusiones):
    y = 2.05 + i * 0.72
    circulo(s, 0.6, y + 0.03, 0.36, CIAN, i + 1, size=12)
    texto(s, 1.1, y, 5.4, 0.3, t, size=13, bold=True, color=BLANCO)
    texto(s, 1.1, y + 0.3, 5.4, 0.3, d, size=10.5, color=TENUE_OSC)
s.notes_slide.notes_text_frame.text = (
    "Presenta (sugerido): Frank.\n"
    "Cuatro ideas para llevarse. Primero, los datos cambian la lectura del negocio: el ranking comercial escondía "
    "el mayor riesgo. Segundo, PostgreSQL sigue siendo la fuente de verdad: las reglas viven en el modelo y, con los "
    "índices correctos, responde en menos de un milisegundo. Tercero, el reto no era el volumen sino la latencia y el "
    "patrón de acceso, y por eso sumamos Kafka, Redis y Databricks, cada uno en lo que hace mejor. Cuarto, la misma "
    "plataforma protege y hace crecer: medimos la exposición al riesgo y abrimos unos US$ 58 mil al mes de ingreso "
    "recuperable, como escenario. Gracias; quedamos atentos a sus preguntas.")

prs.save(SALIDA)
print(f"Guardado {SALIDA} · {len(prs.slides)} diapositivas")
