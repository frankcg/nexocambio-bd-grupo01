# Guion de la demo (5 minutos)

Presenta: Frank. Entre corchetes, lo que se hace en pantalla. Ritmo: unas 130 palabras por minuto.
Todo lo de "Antes de empezar" se deja listo antes de la exposición (`demo\preparar_demo.ps1`).

**Antes de empezar:** terminal A abierta en la carpeta del proyecto · ventana del procesador
escuchando 12 particiones · tablero en http://localhost:8501 · en Databricks, `ingesta_kafka_bronze`
y Playground abiertos.

---

## 0:00 – 0:20 · Apertura

> "Vamos a seguir a un solo cliente: CLI-ZYCHEZ. Primero vamos a ver qué nos dice PostgreSQL de él,
> y después qué pasa cuando opera en tiempo real."

[Terminal A: ejecutar el acto 1]

```
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -h localhost -p 5433 -U postgres -d nexocambio -f demo/acto1_postgresql.sql
```

## 0:20 – 0:50 · Paso 1: la base protege el negocio

[Enter → aparece el ERROR de `ck_historial_transicion`]

> "Un analista intenta devolver a 'En proceso' una operación que ya estaba procesada. La base de
> datos la rechaza. Esta regla no vive en la aplicación: vive en el modelo, como un CHECK. Aunque
> alguien se salte la aplicación, la base no permite un estado inválido."

## 0:50 – 1:20 · Paso 2: el mejor cliente

[Enter → tabla de C6]

> "Esta es la consulta de los tres clientes con más volumen cada mes. En julio, agosto y setiembre,
> el número uno es CLI-ZYCHEZ: cerca de dos millones de dólares al mes. Para el área comercial, es el
> mejor cliente. La pregunta es: ¿es un buen cliente?"

## 1:20 – 1:50 · Paso 3: las features lo delatan

[Enter → features de CLI-ZYCHEZ frente al cliente típico]

> "Sus features responden. Hizo 405 operaciones en 30 días, frente a 6 de un cliente típico. Y el
> 75 % de ellas está entre 9 000 y 9 999 dólares: justo debajo de los 10 000, el umbral en que la
> UIF exige registrar. Eso se llama fraccionamiento. El mejor cliente es el más riesgoso."

## 1:50 – 2:20 · Paso 4: optimización

[Enter dos veces → plan ANTES y DESPUÉS]

> "Y para que el back-office vea el historial de un cliente al instante: sin índice, PostgreSQL leía
> las operaciones de todos los clientes y descartaba casi todas, unos 70 milisegundos. Con un índice
> compuesto por cliente y fecha, va directo a sus operaciones y ya ordenadas: menos de un milisegundo."

## 2:20 – 2:35 · Transición al tiempo real

[Terminal A: ejecutar el acto 2 · mostrar el tablero al lado]

```
.venv\Scripts\python demo/acto2.py
```

> "Hasta aquí, análisis sobre el histórico. Ahora el negocio en vivo: Kafka mueve los eventos,
> Redis guarda el perfil de cada cliente y el modelo decide en milisegundos."

## 2:35 – 3:05 · Paso 1 y 2: riesgo en tiempo real

[Enter → operación de CLI-ZYCHEZ · señalar el tablero]

> "CLI-ZYCHEZ hace una operación de 9 850 dólares. Viajó por Kafka, en Confluent Cloud; el
> procesador actualizó su perfil en Redis y el modelo la puntuó: riesgo ALTO, primera en la cola
> del back-office, y con el motivo: fraccionamiento."

[Enter → operación del cliente típico]

> "La misma operación de un cliente típico: riesgo NORMAL. El modelo no mira cuánto opera el
> cliente, mira cómo opera."

## 3:05 – 3:55 · Paso 3: rescatar la venta

[Enter → se publican las dos cotizaciones · el script muestra en amarillo «AHORA, en Databricks»]

[Databricks: `ingesta_kafka_bronze` → Run all · volver al tablero]

> "La misma plataforma también sirve para vender más. Dos clientes cotizan y no operan. En 90 días,
> las cotizaciones abandonadas sumaron 864 mil dólares de spread que no se cobró: la mitad de lo que
> se ganó. La tasa garantizada dura cinco minutos; en la demo, 20 segundos."

[Al vencer, señalar la tabla «Recuperación de cotizaciones»]

> "Venció. Al cliente típico el sistema le ofrece mantener la tasa cinco minutos más. A CLI-ZYCHEZ,
> nada: es de riesgo alto. El mismo modelo que protege al negocio decide a quién no premiar."

## 3:55 – 4:25 · Paso 4: el mismo evento en el Data Lake

[Enter → el script lista los códigos · Databricks: resultado de `silver_eventos_kafka`]

> "Y el mismo evento llegó también a Databricks, a Delta Lake, con los mismos códigos. Redis decide
> en milisegundos; el Data Lake guarda el histórico con el que el modelo vuelve a entrenarse. Esto
> corre solo, en un Job, todas las noches."

## 4:25 – 4:50 · Cierre con Playground

[Playground: escribir «¿Por qué CLI-ZYCHEZ es un cliente de riesgo alto?»]

> "Por último, el analista no necesita saber SQL. Le pregunta al asistente, que consulta las tablas
> del Data Lake y responde con las cifras reales. El modelo prioriza; la decisión sigue siendo humana."

## 4:50 – 5:00 · Frase final

> "En resumen: PostgreSQL guarda la verdad, Kafka mueve los eventos, Redis decide en milisegundos y
> Databricks aprende del histórico. Cada tecnología en lo que hace mejor."

---

## Si algo falla

| Problema | Qué hacer y qué decir |
|---|---|
| Un evento no aparece en el tablero | Seguir con la ventana del procesador. Si tampoco aparece: «Kafka está en la nube; les muestro la corrida grabada» y pasar al video |
| La ingesta de Databricks no termina a tiempo | Mostrar la última ejecución exitosa del Job `nexocambio_pipeline` |
| Playground tarda | Omitirlo y pasar a la frase final |
| Sin internet | Hacer el acto 1 completo y mostrar el acto 2 desde el video de respaldo |

## Recortes si falta tiempo

- Paso 2 del acto 2 (cliente típico): pulsar Enter y decir solo «riesgo NORMAL: mira cómo opera, no cuánto».
- Paso 4 del acto 1 (optimización): mencionar la cifra (70 → 0,6 ms) sin explicar el plan.
- Playground: es el cierre opcional; la frase final funciona sin él.
