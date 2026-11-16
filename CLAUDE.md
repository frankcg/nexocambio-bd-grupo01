# NexoCambio · Proyecto de Base de Datos (Grupo 1)

Proyecto del curso de Base de Datos (Maestría, UTEC Posgrado). Docente: Luis Chicoma.
Integrantes: Frank Laura, Josue Campos, Mauricio Vallejos.

Caso: NexoCambio, casa de cambio digital de divisas y criptoactivos. Es el mismo negocio del
proyecto de Cloud Computing (backend serverless en DynamoDB, en otro repositorio). El docente
aprobó reutilizar el caso y usar datos ficticios. Aquí el núcleo es un modelo **relacional en
PostgreSQL**, diseñado desde las reglas de negocio, sin migrar datos de DynamoDB.

## Estado
- **Parte 1 (entregable 1): terminada.** Análisis de negocio, modelo ER (15 entidades, 3FN),
  implementación, 10 consultas, 8 features y optimización con EXPLAIN / EXPLAIN ANALYZE.
- **Parte 2 (entregable 2): terminada.** Sus 3 PDF van también en `grupo_01/` (fuentes en
  `docs/fuentes/parte2/`). Caso de IA: detección de operaciones inusuales en tiempo real
  (prevención de lavado de activos). Tecnología: Redis como feature store en línea, Kafka
  en Confluent Cloud (CDC con Debezium, topics con clave `id_cliente`, conector S3 Sink) y Data
  Lake S3. Revisada contra el enunciado el 14/11/2026: cubre todo. Kafka reemplazó a Kinesis y
  **Databricks** (Structured Streaming → Delta Lake, Spark SQL, MLflow) reemplazó a S3 Sink,
  Athena/Glue y SageMaker: el profesor enseña Kafka / Confluent Cloud y Databricks en clase.
- **Medallion implementado** (informe_final, sección 5.1): `generador/exportar_bronze.py` →
  `datos/bronze/*.csv.gz` (no versionado) → Volume `/Volumes/workspace/default/nexocambio/bronze`
  → `notebooks/pipeline_medallion.py` (bronze/silver/gold; gold_features_cliente idéntica a
  v_features_cliente por sumas de control; gold_clientes_riesgo, gold_exposicion_riesgo,
  gold_reactivacion). Probado localmente con PySpark 4.0.1 en un venv de uv con Python 3.12
  (ruta SIN espacios: Spark en Windows falla con espacios; Arrow activado para pandas → Spark).
  **Verificado en Databricks el 16/11/2026**: cifras idénticas a la ejecución local.
- **Ingesta Kafka → Databricks implementada** (16/11/2026): `notebooks/ingesta_kafka_bronze.py`
  (Structured Streaming, `availableNow`, checkpoint en el Volume; credenciales por widgets o secret
  scope `nexocambio`, nunca en el código). Job `nexocambio_pipeline` = ingesta_kafka → medallion,
  ejecutado con éxito (4 min 42 s), programado a diario a las 02:00 (America/Lima). Free Edition sí
  permite conectarse a Confluent Cloud.
  Validación local: PySpark con los jars del conector en el classpath (spark.jars.packages exige
  Hadoop en Windows). Exposición: ALTO = 438 clientes, 16,9 %
  del volumen y 16,2 % del spread (90 días). Reactivación (≥ 2× intervalo y ≥ 14 días, ≤ 120):
  4 991 clientes, US$ 145 520/mes; 28 excluidos por riesgo ALTO. Isolation Forest (semilla 42).
  **Solo las 5 features de comportamiento** (16/11/2026): con las 8 marcaba a 59 de los 94 clientes
  grandes legítimos. Top 2 % (709): 339 de 492 anomalías, precisión 47,8 %, recall 68,9 %,
  ROC AUC 0,922, 0 grandes legítimos marcados. Por perfil: pitufeo 100 %, nocturno 94,5 %,
  multicuenta 73,1 %, pico 4,9 % (la feature `variacion_monto_30d` no lo separa). La primera
  versión (8 features: 329, 46,4 %, 66,9 %, AUC 0,896) se verificó en Databricks. Ejecutado localmente (scikit-learn 1.9.1) y en
  **Databricks Free Edition** (serverless, CSV en `/Volumes/workspace/default/nexocambio/`):
  cifras idénticas. Cuenta de Databricks: la del equipo (correo UTEC de Frank).
- Entorno Python en `.venv/` (Python 3.14): confluent-kafka, redis, psycopg, pandas, scikit-learn.
  Confluent Cloud: cluster **Basic** en AWS us-east-2; credenciales en `.env` (no versionado).
- **Presentación final** (máx. ≈ 11 diapositivas, con demo). **Demo lista** en `demo/` (guía en
  `demo/README.md`): acto 1 en PostgreSQL (`acto1_postgresql.sql`: restricción, C6, features,
  O1 ≈ 70 → 0,6 ms) y acto 2 con Kafka + Redis (`0_preparar.py`, `1_comparar.py`,
  `2_procesador.py`, `3_publicar.py`). Probado el 15/11/2026: features idénticas en PostgreSQL y
  Redis; CLI-ZYCHEZ → riesgo ALTO, CLI-06EZN7 → NORMAL; Kafka ≈ 1,2 s, Redis ≈ 1–4 ms (0,55 ms
  dentro de Redis; el resto es la red de Docker Desktop), inferencia ≈ 15–30 ms.
  Topics creados en Confluent Cloud (6 particiones; clientes compactado).
  **Segundo uso (16/11/2026): recuperar cotizaciones abandonadas** en tiempo real
  (`4_cotizar.py`, topic `nexocambio.cotizaciones`, Redis `cot:{codigo}` +
  `cotizaciones:pendientes` + stream `ofertas:recuperacion`; riesgo ALTO = sin incentivo; vigencia
  de 20 s en la demo). Cifras (`sql/08_oportunidades_ingreso.sql`, 90 días): intención perdida
  110 667 casos cliente-día, US$ 863 592 de spread frente a US$ 1 715 135 cobrado; reactivación:
  4 991 clientes en riesgo, US$ 145 520/mes cuando activos (sección 5.3). Informe_final sección 5.2.
  Ojo: dos procesadores abiertos se reparten las particiones (debe decir 12 particiones). Redis en Docker
  (`demo/docker-compose.yml`, contenedor `nexocambio-redis`).
- **Presentación lista** (16/11/2026): `grupo_01/presentacion/NexoCambio_presentacion_final.pptx`
  (+ PDF), 12 diapositivas sobre la plantilla oficial de UTEC (`D:\Maestria UTEC\Clases\Plantilla
  Presentaciones _  Posgrado UTEC (1).pptx`), orientadas a negocio, con notas del orador y reparto
  sugerido (Josue 2–4, Mauricio 5–7, Frank 1 y 8–12). Generador: `generador/presentacion/construir.py`
  (python-pptx; recursos extraídos de la plantilla). La fuente Space Grotesk viene embebida en la
  plantilla. Portadas de los informes con el formato de UTEC (logo en `docs/fuentes/recursos/`).
  Guía interactiva de la demo: https://claude.ai/artifact/D3XLq7aESaBxm4LJrLifJN (8 pasos).
- **Paquete de entrega:** `grupo_01_final.rar` (137,6 MB, incluye `datos/completo/`, excluye
  `datos/bronze/`). El `grupo_01.rar` viejo (28/10) quedó sin tocar: reemplazarlo a mano.
- **Cuidado con PowerShell 5.1:** `Get-Content` sin `-Encoding UTF8` lee UTF-8 como ANSI y daña
  los acentos al reescribir. Editar archivos con la herramienta Edit o con Python.
- Falta: ensayar la demo y grabar el video de respaldo.

## Pendientes (al 14/11/2026)
- Enunciados en `docs/enunciados/` (`parte1.md`, `parte2.md`).
- Parte 2 lista para entregar. Los tiempos de las features del informe son con **caché fría**
  (decisión del equipo, 14/11/2026), y el informe lo aclara.
- **GitHub:** subido el 14/11/2026 a https://github.com/frankcg/nexocambio-bd-grupo01 (público,
  rama `main`, remoto `origin`). `gh` y `git push` usan la sesión de `frankcg` (keyring), pero la
  variable `GITHUB_TOKEN` tiene un token inválido que los bloquea: en PowerShell ejecutar antes
  `Remove-Item Env:GITHUB_TOKEN`. Al ser público, nunca subir secretos.
- `grupo_01.rar` en la raíz (sin seguimiento): paquete para la entrega; no commitearlo.

## Estructura
- `grupo_01/`: lo que se entrega (se sube **sin** `datos/completo/`, que pesa ~750 MB).
  - `informe.pdf`, `informe.docx`, `modelo_ER.pdf`
  - `sql/01_schema.sql` … `05_indexes.sql`
  - `datos/dataset.csv` (muestra) · `datos/completo/` (CSV completos, no versionados)
  - `generador/generar_datos.py` · `pruebas/pruebas_restricciones.sql` · `resultados/`
- `docs/fuentes/`: fuentes Markdown de los documentos (`informe.md`, `modelo_ER.md`,
  `estilos.css`) · `docs/fuentes/parte2/`: fuentes de la Parte 2.
- `generador/generar_pdfs.py`: Markdown → PDF (Edge headless, marked + Mermaid desde CDN).
- `generador/word/`: Markdown → `informe.docx` (Node, librerías `docx` y `marked`).
- Parte 2 en `grupo_01/`: `informe_final.pdf`, `arquitectura.pdf`, `modelo_nosql.pdf` y
  `sql/06_parte2_caracterizacion.sql` (mide las cifras de la caracterización).
- `docs/enunciados/`: enunciados del curso.

## Comandos
PostgreSQL 18 local en el **puerto 5433**, base `nexocambio`, esquema `nexocambio`. La
contraseña está en `%APPDATA%\postgresql\pgpass.conf` (nunca en el repositorio).
psql: `C:\Program Files\PostgreSQL\18\bin\psql.exe -h localhost -p 5433 -U postgres -w -d nexocambio`
(usar `PGCLIENTENCODING=UTF8`; pasar SQL con tildes por archivo `-f`, no por `-c` desde PowerShell).

Desde `grupo_01/` (las rutas de `\copy` son relativas):
```
psql ... -f sql/01_schema.sql && psql ... -f sql/02_tables.sql
psql ... -f pruebas/pruebas_restricciones.sql      # 29 casos inválidos, con ROLLBACK
python generador/generar_datos.py                    # ~5 min; --escala 0.02 para pruebas
psql ... -f sql/03_data.sql                          # ~11 min
psql ... -f sql/04_queries.sql                       # ~1 min
psql ... -f sql/05_indexes.sql                       # ejecutar varias veces (ver abajo)
```
Desde la raíz:
```
python generador/generar_pdfs.py [informe|modelo_ER|...]   # regenera PDF
python generador/word/diagramas_png.py docs/fuentes/informe.md
node generador/word/generar_word.js                          # regenera informe.docx
```

## Reglas de trabajo
- Todo en español. Trabajar en pasos pequeños y **un commit por paso**.
- El contenido de los documentos se edita en `docs/fuentes/*.md` y luego se regeneran el PDF
  y el Word; no editar los PDF/DOCX a mano (salvo la portada del Word, si el equipo lo decide).
- Las cifras de los informes deben salir de ejecuciones reales (`grupo_01/resultados/`).
  Si se vuelve a ejecutar algo, actualizar el informe para que coincida.
- `generar_datos.py` tiene semilla fija: reejecutarlo sobrescribe `datos/completo/` y
  `datos/dataset.csv` con los mismos datos.
- Si un PDF está abierto en un visor, `generar_pdfs.py` falla a propósito: cerrarlo y reintentar.
- No commitear `datos/completo/`, `node_modules/` ni secretos.

## Datos y resultados clave (para no recalcular)
- 50 000 clientes, 2 000 817 cotizaciones, 918 479 operaciones, 3 499 832 registros de
  historial; enero 2025 – 21/10/2026. Fecha de corte de las consultas: 22/10/2026.
- 509 clientes con anomalías inyectadas (`datos/completo/etiquetas_anomalias.csv`): pitufeo,
  pico, multicuenta, nocturno. Solo para validar features; no forman parte del modelo.
- Optimización (medianas de 5 corridas): O1 historial de cliente 171 → 0,4 ms (índice
  compuesto); O2 cola back-office 263 → 0,4 ms (índice parcial); O3 embudo mensual
  485 → 177 ms (BRIN + reescritura). Los tiempos sin índice varían mucho entre corridas.
- Features en PostgreSQL (Parte 2, mediana de 5 corridas, caché fría con poca RAM libre):
  6,1 ms un cliente típico (CLI-06EZN7), 257,4 ms el cliente con más historial (CLI-ZYCHEZ,
  2 809 operaciones, 42 veces más), 5,5 s todos los clientes. Una medición anterior con caché
  caliente dio 5,6 ms / 100 ms / 3,6 s.
- Caracterización (septiembre de 2026, sin contar el estado inicial del historial): 18 503
  eventos por día, picos de 2 532 por hora y 73 por minuto; 283 → 2 632 operaciones por día
  (enero 2025 → septiembre 2026, 9,3 veces); 23 697 clientes activos en 90 días.
