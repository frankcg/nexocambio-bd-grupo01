"""
NexoCambio · Demo, paso 3: publicar una operación nueva en Kafka (Confluent Cloud).

Hace el papel de la API: publica el evento operacion_creada en el topic nexocambio.operaciones,
con id_cliente como clave. En producción lo publicaría el conector Debezium a partir del WAL
de PostgreSQL; aquí se publica directamente porque la base está en una laptop.

La fecha del evento es el 21/10/2026 (el último día con datos), a la hora actual.

    .venv\\Scripts\\python demo/3_publicar.py [CLI-ZYCHEZ] [9850]
"""
import json
import random
import string
import sys
import uuid
from datetime import datetime

from confluent_kafka import Producer

from comun import CORTE, LIMA, TOPIC_OPERACIONES, conectar_postgres, kafka_conf

codigo_cliente = sys.argv[1] if len(sys.argv) > 1 else "CLI-ZYCHEZ"
monto = float(sys.argv[2]) if len(sys.argv) > 2 else 9850.00

with conectar_postgres() as pg:
    # La cuenta destino más usada por el cliente.
    id_cliente, id_cuenta, tipo, banco, titular_es_cliente = pg.execute("""
        SELECT c.id_cliente, cc.id_cuenta, cc.tipo, b.nombre,
               cc.titular IS NOT DISTINCT FROM coalesce(p.nombres || ' ' || p.apellidos, e.razon_social)
        FROM cliente c
        JOIN operacion o        ON o.id_cliente = c.id_cliente
        JOIN cuenta_cliente cc  ON cc.id_cuenta = o.id_cuenta_destino
        LEFT JOIN banco b       ON b.id_banco = cc.id_banco
        LEFT JOIN persona_natural p ON p.id_cliente = c.id_cliente
        LEFT JOIN empresa e     ON e.id_cliente = c.id_cliente
        WHERE c.codigo_cliente = %s
        GROUP BY 1, 2, 3, 4, 5 ORDER BY count(*) DESC LIMIT 1""", (codigo_cliente,)).fetchone()

ahora = datetime.now(LIMA)
ocurrido = ahora.replace(year=2026, month=10, day=CORTE.day - 1)
codigo_op = "NX-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
evento = {
    "tipo_evento": "operacion_creada",
    "version": 1,
    "id_evento": str(uuid.uuid4()),
    "ocurrido_en": ocurrido.isoformat(timespec="seconds"),
    "operacion": {
        "codigo_operacion": codigo_op, "id_cliente": id_cliente, "modalidad": "casa",
        "moneda_origen": "USD", "moneda_destino": "PEN", "monto_origen": monto, "monto_usd": monto,
        "estado": "Pendiente de comprobante",
        "cuenta_destino": {"id_cuenta": id_cuenta, "tipo": tipo, "banco": banco,
                           "titular_es_cliente": bool(titular_es_cliente)},
    },
}


def entregado(error, msg):
    if error:
        print("Error al publicar:", error)
    else:
        print(f"Publicado {codigo_op} ({codigo_cliente}, US$ {monto:,.2f}) en {msg.topic()} · "
              f"partición {msg.partition()}, offset {msg.offset()}")


productor = Producer(kafka_conf(**{"enable.idempotence": True, "acks": "all"}))
productor.list_topics(TOPIC_OPERACIONES, timeout=15)  # abre la conexión antes de fechar el evento
productor.produce(TOPIC_OPERACIONES, key=str(id_cliente), value=json.dumps(evento), on_delivery=entregado)
productor.flush(15)
