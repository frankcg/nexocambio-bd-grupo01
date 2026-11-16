# NexoCambio Â· Proyecto de Base de Datos (Grupo 1)

Proyecto del curso de Base de Datos (MaestrÃ­a, UTEC Posgrado). Docente: Luis Chicoma.
Integrantes: Frank Laura, Josue Campos, Mauricio Vallejos.

Caso: NexoCambio, casa de cambio digital de divisas y criptoactivos. Es el mismo negocio del
proyecto de Cloud Computing (backend serverless en DynamoDB, en otro repositorio). El docente
aprobÃ³ reutilizar el caso y usar datos ficticios. AquÃ­ el nÃºcleo es un modelo **relacional en
PostgreSQL**, diseÃ±ado desde las reglas de negocio, sin migrar datos de DynamoDB.

## Estado
- **Parte 1 (entregable 1): terminada.** AnÃ¡lisis de negocio, modelo ER (15 entidades, 3FN),
  implementaciÃ³n, 10 consultas, 8 features y optimizaciÃ³n con EXPLAIN / EXPLAIN ANALYZE.
- **Parte 2 (entregable 2): terminada.** Sus 3 PDF van tambiÃ©n en `grupo_01/` (fuentes en
  `docs/fuentes/parte2/`). Caso de IA: detecciÃ³n de operaciones inusuales en tiempo real
  (prevenciÃ³n de lavado de activos). TecnologÃ­a: Redis como feature store en lÃ­nea, Kafka
  en Confluent Cloud (CDC con Debezium, topics con clave `id_cliente`, conector S3 Sink) y Data
  Lake S3. Revisada contra el enunciado el 14/11/2026: cubre todo. Kafka reemplazÃ³ a Kinesis y
  **Databricks** (Structured Streaming â†’ Delta Lake, Spark SQL, MLflow) reemplazÃ³ a S3 Sink,
  Athena/Glue y SageMaker: el profesor enseÃ±a Kafka / Confluent Cloud y Databricks en clase.
- **Medallion implementado** (informe_final, secciÃ³n 5.1): `generador/exportar_bronze.py` â†’
  `datos/bronze/*.csv.gz` (no versionado) â†’ Volume `/Volumes/workspace/default/nexocambio/bronze`
  â†’ `notebooks/pipeline_medallion.py` (bronze/silver/gold; gold_features_cliente idÃ©ntica a
  v_features_cliente por sumas de control; gold_clientes_riesgo, gold_exposicion_riesgo,
  gold_reactivacion). Probado localmente con PySpark 4.0.1 en un venv de uv con Python 3.12
  (ruta SIN espacios: Spark en Windows falla con espacios; Arrow activado para pandas â†’ Spark).
  **Verificado en Databricks el 16/11/2026**: cifras idÃ©nticas a la ejecuciÃ³n local.
- **Ingesta Kafka â†’ Databricks implementada** (16/11/2026): `notebooks/ingesta_kafka_bronze.py`
  (Structured Streaming, `availableNow`, checkpoint en el Volume; credenciales por widgets o secret
  scope `nexocambio`, nunca en el cÃ³digo). Job `nexocambio_pipeline` = ingesta_kafka â†’ medallion,
  ejecutado con Ã©xito (4 min 42 s). Free Edition sÃ­ permite conectarse a Confluent Cloud.
  ValidaciÃ³n local: PySpark con los jars del conector en el classpath (spark.jars.packages exige
  Hadoop en Windows). ExposiciÃ³n: ALTO = 438 clientes, 16,9 %
  del volumen y 16,2 % del spread (90 dÃ­as). ReactivaciÃ³n (â‰¥ 2Ã— intervalo y â‰¥ 14 dÃ­as, â‰¤ 120):
  4 991 clientes, US$ 145 520/mes; 28 excluidos por riesgo ALTO. Isolation Forest (semilla 42).
  **Solo las 5 features de comportamiento** (16/11/2026): con las 8 marcaba a 59 de los 94 clientes
  grandes legÃ­timos. Top 2 % (709): 339 de 492 anomalÃ­as, precisiÃ³n 47,8 %, recall 68,9 %,
  ROC AUC 0,922, 0 grandes legÃ­timos marcados. Por perfil: pitufeo 100 %, nocturno 94,5 %,
  multicuenta 73,1 %, pico 4,9 % (la feature `variacion_monto_30d` no lo separa). La primera
  versiÃ³n (8 features: 329, 46,4 %, 66,9 %, AUC 0,896) se verificÃ³ en Databricks. Ejecutado localmente (scikit-learn 1.9.1) y en
  **Databricks Free Edition** (serverless, CSV en `/Volumes/workspace/default/nexocambio/`):
  cifras idÃ©nticas. Cuenta de Databricks: la del equipo (correo UTEC de Frank).
- Entorno Python en `.venv/` (Python 3.14): confluent-kafka, redis, psycopg, pandas, scikit-learn.
  Confluent Cloud: cluster **Basic** en AWS us-east-2; credenciales en `.env` (no versionado).
- **PresentaciÃ³n final** (mÃ¡x. â‰ˆ 11 diapositivas, con demo). **Demo lista** en `demo/` (guÃ­a en
  `demo/README.md`): acto 1 en PostgreSQL (`acto1_postgresql.sql`: restricciÃ³n, C6, features,
  O1 â‰ˆ 70 â†’ 0,6 ms) y acto 2 con Kafka + Redis (`0_preparar.py`, `1_comparar.py`,
  `2_procesador.py`, `3_publicar.py`). Probado el 15/11/2026: features idÃ©nticas en PostgreSQL y
  Redis; CLI-ZYCHEZ â†’ riesgo ALTO, CLI-06EZN7 â†’ NORMAL; Kafka â‰ˆ 1,2 s, Redis â‰ˆ 1â€“4 ms (0,55 ms
  dentro de Redis; el resto es la red de Docker Desktop), inferencia â‰ˆ 15â€“30 ms.
  Topics creados en Confluent Cloud (6 particiones; clientes compactado).
  **Segundo uso (16/11/2026): recuperar cotizaciones abandonadas** en tiempo real
  (`4_cotizar.py`, topic `nexocambio.cotizaciones`, Redis `cot:{codigo}` +
  `cotizaciones:pendientes` + stream `ofertas:recuperacion`; riesgo ALTO = sin incentivo; vigencia
  de 20 s en la demo). Cifras (`sql/08_oportunidades_ingreso.sql`, 90 dÃ­as): intenciÃ³n perdida
  110 667 casos cliente-dÃ­a, US$ 863 592 de spread frente a US$ 1 715 135 cobrado; reactivaciÃ³n:
  4 991 clientes en riesgo, US$ 145 520/mes cuando activos (secciÃ³n 5.3). Informe_final secciÃ³n 5.2.
  Ojo: dos procesadores abiertos se reparten las particiones (debe decir 12 particiones). Redis en Docker
  (`demo/docker-compose.yml`, contenedor `nexocambio-redis`). Falta: guion de diapositivas y
  video de respaldo.

## Pendientes (al 14/11/2026)
- Enunciados en `docs/enunciados/` (`parte1.md`, `parte2.md`).
- Parte 2 lista para entregar. Los tiempos de las features del informe son con **cachÃ© frÃ­a**
  (decisiÃ³n del equipo, 14/11/2026), y el informe lo aclara.
- **GitHub:** subido el 14/11/2026 a https://github.com/frankcg/nexocambio-bd-grupo01 (pÃºblico,
  rama `main`, remoto `origin`). `gh` y `git push` usan la sesiÃ³n de `frankcg` (keyring), pero la
  variable `GITHUB_TOKEN` tiene un token invÃ¡lido que los bloquea: en PowerShell ejecutar antes
  `Remove-Item Env:GITHUB_TOKEN`. Al ser pÃºblico, nunca subir secretos.
- `grupo_01.rar` en la raÃ­z (sin seguimiento): paquete para la entrega; no commitearlo.

## Estructura
- `grupo_01/`: lo que se entrega (se sube **sin** `datos/completo/`, que pesa ~750 MB).
  - `informe.pdf`, `informe.docx`, `modelo_ER.pdf`
  - `sql/01_schema.sql` â€¦ `05_indexes.sql`
  - `datos/dataset.csv` (muestra) Â· `datos/completo/` (CSV completos, no versionados)
  - `generador/generar_datos.py` Â· `pruebas/pruebas_restricciones.sql` Â· `resultados/`
- `docs/fuentes/`: fuentes Markdown de los documentos (`informe.md`, `modelo_ER.md`,
  `estilos.css`) Â· `docs/fuentes/parte2/`: fuentes de la Parte 2.
- `generador/generar_pdfs.py`: Markdown â†’ PDF (Edge headless, marked + Mermaid desde CDN).
- `generador/word/`: Markdown â†’ `informe.docx` (Node, librerÃ­as `docx` y `marked`).
- Parte 2 en `grupo_01/`: `informe_final.pdf`, `arquitectura.pdf`, `modelo_nosql.pdf` y
  `sql/06_parte2_caracterizacion.sql` (mide las cifras de la caracterizaciÃ³n).
- `docs/enunciados/`: enunciados del curso.

## Comandos
PostgreSQL 18 local en el **puerto 5433**, base `nexocambio`, esquema `nexocambio`. La
contraseÃ±a estÃ¡ en `%APPDATA%\postgresql\pgpass.conf` (nunca en el repositorio).
psql: `C:\Program Files\PostgreSQL\18\bin\psql.exe -h localhost -p 5433 -U postgres -w -d nexocambio`
(usar `PGCLIENTENCODING=UTF8`; pasar SQL con tildes por archivo `-f`, no por `-c` desde PowerShell).

Desde `grupo_01/` (las rutas de `\copy` son relativas):
```
psql ... -f sql/01_schema.sql && psql ... -f sql/02_tables.sql
psql ... -f pruebas/pruebas_restricciones.sql      # 29 casos invÃ¡lidos, con ROLLBACK
python generador/generar_datos.py                    # ~5 min; --escala 0.02 para pruebas
psql ... -f sql/03_data.sql                          # ~11 min
psql ... -f sql/04_queries.sql                       # ~1 min
psql ... -f sql/05_indexes.sql                       # ejecutar varias veces (ver abajo)
```
Desde la raÃ­z:
```
python generador/generar_pdfs.py [informe|modelo_ER|...]   # regenera PDF
python generador/word/diagramas_png.py docs/fuentes/informe.md
node generador/word/generar_word.js                          # regenera informe.docx
```

## Reglas de trabajo
- Todo en espaÃ±ol. Trabajar en pasos pequeÃ±os y **un commit por paso**.
- El contenido de los documentos se edita en `docs/fuentes/*.md` y luego se regeneran el PDF
  y el Word; no editar los PDF/DOCX a mano (salvo la portada del Word, si el equipo lo decide).
- Las cifras de los informes deben salir de ejecuciones reales (`grupo_01/resultados/`).
  Si se vuelve a ejecutar algo, actualizar el informe para que coincida.
- `generar_datos.py` tiene semilla fija: reejecutarlo sobrescribe `datos/completo/` y
  `datos/dataset.csv` con los mismos datos.
- Si un PDF estÃ¡ abierto en un visor, `generar_pdfs.py` falla a propÃ³sito: cerrarlo y reintentar.
- No commitear `datos/completo/`, `node_modules/` ni secretos.

## Datos y resultados clave (para no recalcular)
- 50 000 clientes, 2 000 817 cotizaciones, 918 479 operaciones, 3 499 832 registros de
  historial; enero 2025 â€“ 21/10/2026. Fecha de corte de las consultas: 22/10/2026.
- 509 clientes con anomalÃ­as inyectadas (`datos/completo/etiquetas_anomalias.csv`): pitufeo,
  pico, multicuenta, nocturno. Solo para validar features; no forman parte del modelo.
- OptimizaciÃ³n (medianas de 5 corridas): O1 historial de cliente 171 â†’ 0,4 ms (Ã­ndice
  compuesto); O2 cola back-office 263 â†’ 0,4 ms (Ã­ndice parcial); O3 embudo mensual
  485 â†’ 177 ms (BRIN + reescritura). Los tiempos sin Ã­ndice varÃ­an mucho entre corridas.
- Features en PostgreSQL (Parte 2, mediana de 5 corridas, cachÃ© frÃ­a con poca RAM libre):
  6,1 ms un cliente tÃ­pico (CLI-06EZN7), 257,4 ms el cliente con mÃ¡s historial (CLI-ZYCHEZ,
  2 809 operaciones, 42 veces mÃ¡s), 5,5 s todos los clientes. Una mediciÃ³n anterior con cachÃ©
  caliente dio 5,6 ms / 100 ms / 3,6 s.
- CaracterizaciÃ³n (septiembre de 2026, sin contar el estado inicial del historial): 18 503
  eventos por dÃ­a, picos de 2 532 por hora y 73 por minuto; 283 â†’ 2 632 operaciones por dÃ­a
  (enero 2025 â†’ septiembre 2026, 9,3 veces); 23 697 clientes activos en 90 dÃ­as.
