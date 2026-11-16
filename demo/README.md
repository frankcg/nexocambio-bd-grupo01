# Demo de la presentación final (≈ 5 minutos)

Hilo conductor: seguir a **CLI-ZYCHEZ**, el cliente de mayor volumen, que resulta ser el más
riesgoso (fracciona sus operaciones justo debajo de US$ 10 000).

## Antes de la exposición (una vez, ≈ 2 min)

1. **Liberar memoria:** cerrar Chrome, Zoom y otros programas pesados. Con poca RAM libre,
   PostgreSQL lee del disco y los tiempos suben.
2. Abrir **Docker Desktop** y levantar Redis:
   ```
   docker compose -f demo/docker-compose.yml up -d
   ```
3. Preparar el entorno: crea los topics en Confluent Cloud (si no existen), carga Redis desde
   PostgreSQL y entrena el modelo. También **reinicia Redis**, así que borra las operaciones
   publicadas en ensayos anteriores.
   ```
   .venv\Scripts\python demo/0_preparar.py
   ```
4. Abrir dos terminales de PowerShell en la raíz del proyecto. Si los acentos se ven mal,
   ejecutar antes `$env:PYTHONIOENCODING = "utf-8"` en cada una. Dejar en la **terminal B** el
   procesador corriendo hasta que diga *"Escuchando nexocambio.operaciones"*:
   ```
   .venv\Scripts\python demo/2_procesador.py
   ```

Requisitos: `.env` en la raíz con `KAFKA_BOOTSTRAP`, `KAFKA_API_KEY` y `KAFKA_API_SECRET`;
PostgreSQL en el puerto 5433; entorno `.venv` con confluent-kafka, redis, psycopg, pandas y
scikit-learn.

## Acto 1 · PostgreSQL (Parte 1, ≈ 2,5 min) · terminal A

En PowerShell (el `&` es necesario porque la ruta va entre comillas):
```
$env:PGCLIENTENCODING = "UTF8"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -p 5433 -U postgres -d nexocambio -f demo/acto1_postgresql.sql
```

El script se detiene antes de cada paso: **Enter** para seguir.

| Paso | Qué se ve | Qué decir |
|---|---|---|
| 1 | Un analista intenta pasar una operación de *Procesada* a *En proceso* y la base la rechaza | Las reglas del negocio están en el modelo (CHECK de la máquina de estados), no solo en la aplicación |
| 2 | C6: CLI-ZYCHEZ es el n.º 1 en volumen julio, agosto y septiembre | El ranking comercial dice que es el mejor cliente… |
| 3 | Sus features frente a un cliente típico: `ratio_cerca_umbral` 0,754 frente a 0,000 | …pero el 75 % de sus operaciones está justo debajo del umbral de la UIF: es fraccionamiento |
| 4 | O1 antes y después del índice compuesto: ≈ 70 ms → ≈ 0,6 ms | El índice (id_cliente, fecha DESC) sigue el patrón de acceso: va directo al cliente y entrega las filas ordenadas |

## Acto 2 · Kafka + Redis (Parte 2, ≈ 2,5 min) · terminal A

**Paso 5 · ¿Por qué no basta PostgreSQL?**
```
.venv\Scripts\python demo/1_comparar.py
```
Las mismas features, idénticas, en PostgreSQL y en Redis. PostgreSQL tarda ≈ 5 ms para el
cliente típico y ≈ 100–260 ms para CLI-ZYCHEZ: crece con el historial. Redis tarda lo mismo
para los dos (≈ 2–4 ms en la laptop; Redis en sí resuelve la lectura en ≈ 0,5 ms y el resto
es la red de Docker Desktop).

**Paso 6 · Una operación nueva, en tiempo real**
```
.venv\Scripts\python demo/3_publicar.py CLI-ZYCHEZ 9850
```
En la **terminal B** aparece el evento: llegó por Kafka desde Confluent Cloud (≈ 1 s, ida y
vuelta a AWS us-east-2), Redis actualizó sus ventanas con un script Lua (≈ 1–2 ms), el modelo
lo puntuó (≈ 15–30 ms) y quedó en la cola del back-office con **riesgo ALTO** y sus motivos.

Para contrastar, un cliente típico:
```
.venv\Scripts\python demo/3_publicar.py CLI-06EZN7 500
```
→ **riesgo NORMAL**.

**Paso 7 · Segundo uso: recuperar cotizaciones abandonadas**

La misma arquitectura, ahora para vender más. La tasa garantizada dura 5 minutos; en la demo,
20 segundos.
```
.venv\Scripts\python demo/4_cotizar.py CLI-06EZN7 3000
.venv\Scripts\python demo/4_cotizar.py CLI-ZYCHEZ 9800
```
En la **terminal B**, a los 20 s: el cliente típico recibe una acción comercial ("mantener la tasa
5 minutos más"); CLI-ZYCHEZ, **ninguna**, porque es de riesgo ALTO. El mismo modelo que protege
al negocio decide a quién no se le ofrece un incentivo. Si se quiere mostrar una cotización que sí
se convierte (no dispara nada):
```
.venv\Scripts\python demo/4_cotizar.py CLI-06EZN7 4500 --opera 5
```
Cifra para la diapositiva: en 90 días, la intención de compra perdida equivale a US$ 864 mil de
spread, la mitad de lo cobrado (`grupo_01/resultados/08_oportunidades_resultados.txt`).

Mensaje final: PostgreSQL es la fuente de verdad, Kafka mueve los eventos, Redis responde en
milisegundos y Databricks entrena el modelo con el histórico (*Polyglot Persistence*).

## Si algo falla en vivo

- **Un evento no aparece en la terminal B:** hay otro procesador abierto (por ejemplo, de un ensayo
  anterior). Están en el mismo *consumer group* y Kafka reparte las particiones entre ambos.
  Cerrar todos con Ctrl+C y dejar uno solo; al arrancar debe decir **12 particiones**.
- **Confluent Cloud no responde** (internet): mostrar el paso 5, que no usa Kafka, y el video
  de respaldo.
- **Docker / Redis caído:** `docker compose -f demo/docker-compose.yml up -d` y volver a
  ejecutar `0_preparar.py`.
- **Tiempos de PostgreSQL muy altos:** falta memoria libre; cerrar programas.

Grabar un **video de respaldo** de la demo completa antes del día de la exposición.
