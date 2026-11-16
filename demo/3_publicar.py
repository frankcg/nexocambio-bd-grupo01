"""
NexoCambio · Demo, paso 3: publicar una operación nueva en Kafka (Confluent Cloud).

Hace el papel de la API: publica el evento operacion_creada en el topic nexocambio.operaciones,
con id_cliente como clave. En producción lo publicaría el conector Debezium a partir del WAL
de PostgreSQL; aquí se publica directamente porque la base está en una laptop.

La fecha del evento es el 21/10/2026 (el último día con datos), a la hora actual.

    .venv\\Scripts\\python demo/3_publicar.py [CLI-ZYCHEZ] [9850]
"""
import sys

from confluent_kafka import Producer

from comun import (TOPIC_OPERACIONES, codigo, conectar_postgres, datos_cliente, evento, kafka_conf,
                   publicar)


def evento_operacion(id_cliente, cuenta, monto, codigo_cotizacion=None):
    return evento("operacion_creada", "operacion", {
        "codigo_operacion": codigo("NX"), "codigo_cotizacion": codigo_cotizacion, "id_cliente": id_cliente,
        "modalidad": "casa", "moneda_origen": "USD", "moneda_destino": "PEN", "monto_origen": monto,
        "monto_usd": monto, "estado": "Pendiente de comprobante", "cuenta_destino": cuenta})


if __name__ == "__main__":
    codigo_cliente = sys.argv[1] if len(sys.argv) > 1 else "CLI-ZYCHEZ"
    monto = float(sys.argv[2]) if len(sys.argv) > 2 else 9850.00
    with conectar_postgres() as pg:
        id_cliente, cuenta = datos_cliente(pg, codigo_cliente)

    productor = Producer(kafka_conf(**{"enable.idempotence": True, "acks": "all"}))
    productor.list_topics(TOPIC_OPERACIONES, timeout=15)  # abre la conexión antes de fechar el evento
    ev = evento_operacion(id_cliente, cuenta, monto)
    publicar(productor, TOPIC_OPERACIONES, id_cliente, ev,
             f"{ev['operacion']['codigo_operacion']} ({codigo_cliente}, US$ {monto:,.2f})")
