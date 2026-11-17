"""
NexoCambio · Demo, paso 4: un cliente cotiza (segundo uso: recuperar cotizaciones abandonadas).

Publica el evento cotizacion_emitida en nexocambio.cotizaciones. Si el cliente no opera antes de
que venza la tasa garantizada (20 s en la demo; 5 minutos en producción), el procesador dispara
una acción comercial, salvo que el cliente sea de riesgo ALTO.

    .venv\\Scripts\\python demo/4_cotizar.py CLI-06EZN7 3000            # cotiza y no opera
    .venv\\Scripts\\python demo/4_cotizar.py CLI-06EZN7 3000 --opera 5  # cotiza y opera a los 5 s
"""
import argparse
import importlib.util
import time

from confluent_kafka import Producer

from comun import (DEMO, TOPIC_COTIZACIONES, TOPIC_OPERACIONES, UMBRAL_PREFERENCIAL_USD,
                   VIGENCIA_COTIZACION_S, codigo, conectar_postgres, datos_cliente, evento, kafka_conf,
                   publicar)

# 3_publicar.py empieza con un dígito: se carga por ruta para reutilizar su evento de operación.
_spec = importlib.util.spec_from_file_location("publicar_operacion", DEMO / "3_publicar.py")
publicar_operacion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(publicar_operacion)


def evento_cotizacion(id_cliente, codigo_cliente, monto):
    codigo_cot = codigo("CT")
    return codigo_cot, evento("cotizacion_emitida", "cotizacion", {
        "codigo_cotizacion": codigo_cot, "id_cliente": id_cliente, "codigo_cliente": codigo_cliente,
        "modalidad": "casa", "moneda_origen": "USD", "moneda_destino": "PEN", "monto_usd": monto,
        "tasa_preferencial": monto >= UMBRAL_PREFERENCIAL_USD, "vigencia_s": VIGENCIA_COTIZACION_S})


def publicar_cotizacion(productor, id_cliente, codigo_cliente, monto):
    codigo_cot, ev = evento_cotizacion(id_cliente, codigo_cliente, monto)
    publicar(productor, TOPIC_COTIZACIONES, id_cliente, ev,
             f"{codigo_cot} ({codigo_cliente}, US$ {monto:,.2f}, vence en {VIGENCIA_COTIZACION_S} s)")
    return codigo_cot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publica una cotización en Kafka.")
    parser.add_argument("cliente", nargs="?", default="CLI-06EZN7")
    parser.add_argument("monto", nargs="?", type=float, default=3000.0)
    parser.add_argument("--opera", type=float, metavar="SEG", help="publicar la operación a los SEG segundos")
    args = parser.parse_args()

    with conectar_postgres() as pg:
        id_cliente, cuenta = datos_cliente(pg, args.cliente)

    productor = Producer(kafka_conf(**{"enable.idempotence": True, "acks": "all"}))
    productor.list_topics(TOPIC_COTIZACIONES, timeout=15)
    codigo_cot = publicar_cotizacion(productor, id_cliente, args.cliente, args.monto)

    if args.opera is not None:
        time.sleep(args.opera)
        ev_op = publicar_operacion.evento_operacion(id_cliente, cuenta, args.monto, codigo_cot, args.cliente)
        publicar(productor, TOPIC_OPERACIONES, id_cliente, ev_op,
                 f"{ev_op['operacion']['codigo_operacion']} con la cotización {codigo_cot}")
