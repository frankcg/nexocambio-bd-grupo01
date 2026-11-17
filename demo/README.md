# Demo de la presentación final (≈ 5 minutos)

Hilo conductor: seguir a **CLI-ZYCHEZ**, el cliente de mayor volumen, que resulta ser el más
riesgoso (fracciona sus operaciones justo debajo de US$ 10 000).

## Antes de la exposición: un solo comando (≈ 2 min)

Cerrar Chrome, Zoom y otros programas pesados (con poca RAM, PostgreSQL lee del disco). Luego,
en PowerShell, desde la raíz del proyecto:

```
powershell -ExecutionPolicy Bypass -File demo\preparar_demo.ps1
```

El script abre Docker Desktop si hace falta, levanta Redis, cierra procesadores de ensayos
anteriores, ejecuta `0_preparar.py` (topics, Redis desde PostgreSQL y modelo), y abre:

- una ventana **«procesador»**, que debe decir *Escuchando … (12 particiones)*;
- el **tablero** en el navegador: http://localhost:8501 (cola por riesgo y ofertas, en vivo).

Dejar abierto en Databricks el notebook `ingesta_kafka_bronze`.

Requisitos: `.env` en la raíz con `KAFKA_BOOTSTRAP`, `KAFKA_API_KEY` y `KAFKA_API_SECRET`;
PostgreSQL en el puerto 5433; entorno `.venv` con confluent-kafka, redis, psycopg, pandas,
scikit-learn y streamlit.

## Acto 1 · PostgreSQL (≈ 2,5 min)

```
$env:PGCLIENTENCODING = "UTF8"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -p 5433 -U postgres -d nexocambio -f demo/acto1_postgresql.sql
```

Enter para avanzar:

| Paso | Qué se ve | Qué decir |
|---|---|---|
| 1 | Pasar una operación de *Procesada* a *En proceso*: la base la rechaza | Las reglas viven en el modelo, no solo en la aplicación |
| 2 | C6: CLI-ZYCHEZ es el n.º 1 en volumen jul–set | Para el área comercial es el mejor cliente… |
| 3 | Sus features: `ratio_cerca_umbral` 0,754 frente a 0,000 | …pero el 75 % de sus operaciones está justo bajo el umbral de la UIF |
| 4 | O1: ≈ 70 ms → ≈ 0,6 ms con el índice compuesto | El índice sigue el patrón de acceso |

## Acto 2 · Kafka + Redis + Databricks (≈ 2,5 min)

```
.venv\Scripts\python demo/acto2.py
```

El script publica los eventos por sí mismo; Enter para avanzar. Las reacciones se ven en el
**tablero** y en la ventana del **procesador**.

| Paso | Qué hace el script | Qué se ve en el tablero | Qué decir |
|---|---|---|---|
| 1 | Operación de CLI-ZYCHEZ, US$ 9 850 | Primera en la cola, **riesgo ALTO**, motivos | Kafka → Redis → modelo en milisegundos |
| 2 | Operación de un cliente típico, US$ 500 | **Riesgo NORMAL** | Juzga cómo opera el cliente, no cuánto |
| 3 | Dos cotizaciones que vencen en 20 s | Oferta para CLI-06EZN7; **sin incentivo** para CLI-ZYCHEZ | Segundo uso: rescatar la venta (US$ 864 mil de spread perdido en 90 días) |
| 4 | Lista los códigos publicados | — | El mismo evento llegó a Delta Lake |

En el paso 3 el script avisa **«AHORA, en Databricks: ingesta_kafka_bronze → Run all»**: lanzarla
en ese momento. Con el disparador `availableNow` solo toma lo que ya está en Kafka, y así corre
durante los 20 s de espera (tarda ≈ 45 s). En el paso 4, `silver_eventos_kafka` muestra los mismos
códigos que imprimió el script.

Opcional: `python demo/acto2.py --comparar` muestra primero las mismas features en PostgreSQL y
en Redis (PostgreSQL tarda más cuanto más historial tiene el cliente; Redis, lo mismo para todos).

Mensaje final: PostgreSQL es la fuente de verdad, Kafka mueve los eventos, Redis responde en
milisegundos y Databricks aprende del histórico (*Polyglot Persistence*).

## Scripts sueltos (para ensayar o si algo falla)

| Script | Qué hace |
|---|---|
| `0_preparar.py` | Topics, carga de Redis desde PostgreSQL y modelo (reinicia Redis) |
| `1_comparar.py` | Las mismas features en PostgreSQL y en Redis, con tiempos |
| `2_procesador.py` | Consumer group: operaciones (riesgo) y cotizaciones (recuperación) |
| `3_publicar.py CLI-ZYCHEZ 9850` | Publica una operación |
| `4_cotizar.py CLI-06EZN7 3000 [--opera 5]` | Publica una cotización (y opcionalmente su operación) |
| `tablero.py` | Tablero Streamlit: `python -m streamlit run tablero.py` desde `demo/` (toma su tema de `demo/.streamlit/`) |

## Si algo falla en vivo

- **Un evento no aparece:** hay otro procesador abierto y Kafka reparte las particiones entre
  ambos. Volver a ejecutar `preparar_demo.ps1`, que cierra los anteriores.
- **Confluent Cloud no responde** (internet): mostrar el acto 1 y el video de respaldo.
- **Docker / Redis caído:** volver a ejecutar `preparar_demo.ps1`.
- **Tiempos de PostgreSQL muy altos:** falta memoria libre; cerrar programas.

Grabar un **video de respaldo** de la demo completa antes del día de la exposición.
