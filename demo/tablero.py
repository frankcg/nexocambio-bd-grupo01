"""
NexoCambio · Demo: tablero en vivo del back-office (lee Redis cada 2 segundos).

Muestra lo que el procesador deja en Redis: la cola de operaciones ordenada por riesgo y las
acciones comerciales sobre cotizaciones vencidas. No escribe nada.

    .venv\\Scripts\\python -m streamlit run demo/tablero.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import redis
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from comun import LIMA, conectar_redis  # noqa: E402

st.set_page_config(page_title="NexoCambio · Monitor", page_icon=":material/monitoring:", layout="wide")


# Textos cortos para la tabla (el procesador guarda la acción completa).
ACCIONES = {"ninguna": "Sin incentivo",
            "mantener la tasa 5 minutos más": "Tasa 5 min más",
            "mantener la tasa preferencial 5 minutos más": "Tasa preferencial 5 min más",
            "ofrecer la tasa preferencial si sube a US$ 5,000": "Preferencial si sube a US$ 5 000"}


@st.cache_resource
def cliente_redis():
    return conectar_redis()


def leer_estado(r):
    """Todo lo que muestra el tablero, leído en pocos viajes a Redis."""
    todas = r.zrevrange("cola:riesgo", 0, -1, withscores=True)  # en la demo la cola es corta
    p = r.pipeline(transaction=False)
    for codigo, _ in todas:
        p.hgetall(f"op:{{{codigo}}}:riesgo")
    detalles_todos = p.execute() if todas else []
    altos = sum(1 for d in detalles_todos if d.get("nivel") == "ALTO")
    total_cola = len(todas)
    cola, detalles = todas[:10], detalles_todos[:10]
    filas_cola = [{
        "Operación": codigo,
        "Cliente": d.get("codigo_cliente", "—"),
        "Monto (US$)": float(d.get("monto_usd", 0) or 0),
        "Score": float(score),
        "Riesgo": d.get("nivel", "—"),
        "Motivos": ", ".join(json.loads(d.get("motivos", "[]"))) or "—",
    } for (codigo, score), d in zip(cola, detalles)]

    ofertas = r.xrevrange("ofertas:recuperacion", count=10)
    filas_ofertas = [{
        "Hora": datetime.fromtimestamp(int(id_msg.split("-")[0]) / 1000, LIMA).strftime("%H:%M:%S"),
        "Cotización": c.get("codigo_cotizacion", "—"),
        "Cliente": c.get("codigo_cliente", "—"),
        "Monto (US$)": float(c.get("monto_usd", 0) or 0),
        "Riesgo": c.get("riesgo", "—"),
        "Acción": ACCIONES.get(c.get("accion", ""), c.get("accion", "—")),
    } for id_msg, c in ofertas]

    metricas = r.hgetall("metricas:cotizaciones")
    return {"total_cola": total_cola, "altos": altos, "cola": filas_cola, "ofertas": filas_ofertas,
            "metricas": {k: int(v) for k, v in metricas.items()}}


st.title("NexoCambio · Monitor en tiempo real")
st.caption("Kafka (Confluent Cloud) → procesador → Redis. El tablero lee Redis cada 2 segundos.")


@st.fragment(run_every="2s")
def panel():
    try:
        e = leer_estado(cliente_redis())
    except redis.exceptions.ConnectionError:
        st.error("Levante Redis con `docker compose -f demo/docker-compose.yml up -d` y recargue la página.",
                 title="No hay conexión con Redis")
        return

    m = e["metricas"]
    with st.container(horizontal=True):
        st.metric("Operaciones en la cola", e["total_cola"], border=True)
        st.metric("Riesgo ALTO", e["altos"], border=True)
        st.metric("Cotizaciones emitidas", m.get("emitidas", 0), border=True)
        st.metric("Convertidas a tiempo", m.get("convertidas", 0), border=True)
        st.metric("Ofertas enviadas", m.get("ofertas", 0), border=True)
        st.metric("Sin incentivo (riesgo ALTO)", m.get("sin_oferta", 0), border=True)

    izquierda, derecha = st.columns(2)
    with izquierda, st.container(border=True):
        st.subheader(":material/gavel: Cola del back-office, por riesgo")
        if e["cola"]:
            st.dataframe(
                pd.DataFrame(e["cola"]), hide_index=True, alt="Operaciones ordenadas por score de riesgo",
                column_config={
                    "Monto (US$)": st.column_config.NumberColumn(format="%,.2f"),
                    "Score": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.3f"),
                    "Motivos": st.column_config.TextColumn(width="medium"),
                })
        else:
            st.info("Todavía no hay operaciones. Publíquelas con `python demo/acto2.py`.")
    with derecha, st.container(border=True):
        st.subheader(":material/sell: Recuperación de cotizaciones")
        if e["ofertas"]:
            st.dataframe(pd.DataFrame(e["ofertas"]), hide_index=True,
                         alt="Acciones comerciales sobre cotizaciones vencidas",
                         column_config={"Monto (US$)": st.column_config.NumberColumn(format="%,.2f"),
                                        "Acción": st.column_config.TextColumn(width="medium")})
        else:
            st.info("Aquí aparece la decisión cuando vence una cotización sin operación.")


panel()
