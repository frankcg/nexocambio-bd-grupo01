"""
NexoCambio · Demo, acto 2 en una sola terminal: Enter para avanzar.

Publica los eventos en Kafka por sí mismo; las reacciones se ven en la ventana del procesador y
en el tablero (los abre preparar_demo.ps1).

    1. Una operación de CLI-ZYCHEZ        → riesgo ALTO en tiempo real
    2. Una operación de un cliente típico → riesgo NORMAL
    3. Dos cotizaciones que vencen        → oferta al cliente típico, ninguna a CLI-ZYCHEZ
    4. El mismo evento en Databricks      → bronze_eventos_kafka / silver_eventos_kafka

    .venv\\Scripts\\python demo/acto2.py              # sin la comparación PostgreSQL vs Redis
    .venv\\Scripts\\python demo/acto2.py --comparar   # con la comparación al inicio
"""
import argparse
import importlib.util
import os
import subprocess
import sys
import time

from confluent_kafka import Producer

from comun import (DEMO, TOPIC_OPERACIONES, VIGENCIA_COTIZACION_S, conectar_postgres, datos_cliente, kafka_conf,
                   publicar)


def cargar(nombre):
    """Los scripts de la demo empiezan con un dígito: se cargan por ruta."""
    spec = importlib.util.spec_from_file_location(nombre.replace(".py", ""), DEMO / nombre)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def paso(numero, titulo, decir):
    print(f"\n\033[96m=== {numero} · {titulo} ===\033[0m")
    print(f"\033[90m{decir}\033[0m")
    input("(Enter) ")


def main():
    if os.name == "nt":
        os.system("")  # activa los colores ANSI en la consola de Windows
    parser = argparse.ArgumentParser(description="Acto 2 de la demo de NexoCambio.")
    parser.add_argument("--comparar", action="store_true", help="mostrar primero PostgreSQL frente a Redis")
    args = parser.parse_args()
    operacion, cotizacion = cargar("3_publicar.py"), cargar("4_cotizar.py")

    if args.comparar:
        paso("0", "Las mismas features, en PostgreSQL y en Redis",
             "PostgreSQL tarda más cuanto más historial tiene el cliente; Redis tarda lo mismo para todos.")
        subprocess.run([sys.executable, str(DEMO / "1_comparar.py")], check=False)

    with conectar_postgres() as pg:
        zychez, tipico = datos_cliente(pg, "CLI-ZYCHEZ"), datos_cliente(pg, "CLI-06EZN7")
    productor = Producer(kafka_conf(**{"enable.idempotence": True, "acks": "all"}))
    productor.list_topics(TOPIC_OPERACIONES, timeout=15)  # conexión abierta antes de publicar
    publicados = []

    paso("1", "Una operación de CLI-ZYCHEZ, en tiempo real",
         "Se publica en Kafka (Confluent Cloud). El procesador actualiza Redis y el modelo la puntúa.")
    ev = operacion.evento_operacion(*zychez, 9850.0, codigo_cliente="CLI-ZYCHEZ")
    publicar(productor, TOPIC_OPERACIONES, zychez[0], ev, f"{ev['operacion']['codigo_operacion']} (CLI-ZYCHEZ, US$ 9,850.00)")
    publicados.append(ev["operacion"]["codigo_operacion"])
    print("→ Mira el procesador y el tablero: riesgo ALTO, primera en la cola, con sus motivos.")

    paso("2", "La misma operación para un cliente típico",
         "Mismo flujo, otro comportamiento: el modelo juzga cómo opera el cliente, no cuánto.")
    ev = operacion.evento_operacion(*tipico, 500.0, codigo_cliente="CLI-06EZN7")
    publicar(productor, TOPIC_OPERACIONES, tipico[0], ev, f"{ev['operacion']['codigo_operacion']} (CLI-06EZN7, US$ 500.00)")
    publicados.append(ev["operacion"]["codigo_operacion"])
    print("→ En el tablero: riesgo NORMAL.")

    paso("3", "Segundo uso: dos cotizaciones que nadie termina",
         f"La tasa garantizada dura {VIGENCIA_COTIZACION_S} s en la demo (5 minutos en producción).")
    publicados.append(cotizacion.publicar_cotizacion(productor, tipico[0], "CLI-06EZN7", 3000.0))
    publicados.append(cotizacion.publicar_cotizacion(productor, zychez[0], "CLI-ZYCHEZ", 9800.0))
    print("\033[93m→ AHORA, en Databricks: ingesta_kafka_bronze → Run all (corre mientras vence la tasa).\033[0m")
    for restante in range(VIGENCIA_COTIZACION_S + 2, 0, -1):
        print(f"\r  La tasa vence en {restante:2d} s… ", end="", flush=True)
        time.sleep(1)
    print("\r→ Vencieron: en el procesador y el tablero, oferta para CLI-06EZN7 y ninguna para CLI-ZYCHEZ.")

    paso("4", "El mismo evento llegó a Delta Lake",
         "Cuando termine la ingesta, silver_eventos_kafka muestra los mismos códigos.")
    print("Códigos publicados en este acto:\n  " + "\n  ".join(publicados))
    print("\nMensaje final: PostgreSQL guarda la verdad, Kafka mueve los eventos, Redis decide en "
          "milisegundos y Databricks aprende del histórico.")


if __name__ == "__main__":
    main()
