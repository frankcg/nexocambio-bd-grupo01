# NexoCambio — Proyecto de Base de Datos (Grupo 1)

Integrantes: Frank Laura, Josue Campos y Mauricio Vallejos.

Caso de negocio: casa de cambio digital de divisas y criptoactivos (NexoCambio), el mismo del
curso de Cloud Computing. Autorizado por el docente, con datos sintéticos.

## Entregable 1 (`grupo_01/`, lo que se sube)
| Archivo | Contenido |
|---|---|
| `informe.pdf` / `informe.docx` | Análisis de negocio, modelo ER, implementación, 10 consultas, 8 features, optimización (el .docx permite personalizar la portada) |
| `modelo_ER.pdf` | Diagrama ER completo, cardinalidades y diccionario de datos |
| `sql/01_schema.sql` … `05_indexes.sql` | Esquema, tablas, carga, consultas e índices |
| `datos/dataset.csv` | Muestra plana de ~10 mil operaciones |
| `generador/generar_datos.py` | Genera los datos completos que carga `03_data.sql` (solo biblioteca estándar de Python) |
| `pruebas/pruebas_restricciones.sql` | 29 casos inválidos que las restricciones deben rechazar (con ROLLBACK) |
| `resultados/` | Salidas completas de `04_queries.sql` y `05_indexes.sql` |

## Entregable 2 (`entrega_2/`, borrador)
Borrador de la Parte 2 (arquitectura para IA: detección de operaciones inusuales con Redis,
Kinesis y Data Lake). Se retomará para el segundo entregable; sus fuentes están en
`docs/fuentes/parte2/`.

## Otras carpetas
- `docs/fuentes/`: fuentes Markdown de los documentos.
  - `python generador/generar_pdfs.py` regenera los PDF (Edge headless).
  - `node generador/word/generar_word.js` regenera `informe.docx`.
- `docs/01_analisis_negocio_y_modelo_ER.md`: primer borrador (lo vigente está en el informe).

## Ejecución
PostgreSQL 18 local en el puerto 5433. La contraseña va en `%APPDATA%\postgresql\pgpass.conf`,
nunca en el repositorio. Todo se ejecuta desde `grupo_01/` (las rutas de `\copy` son relativas):
```
cd grupo_01
psql -h localhost -p 5433 -U postgres -d postgres -c "CREATE DATABASE nexocambio ENCODING 'UTF8' TEMPLATE template0;"
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/01_schema.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/02_tables.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f pruebas/pruebas_restricciones.sql

python generador/generar_datos.py                                            # ~5 min; CSV en datos/completo/ (no se versionan)
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/03_data.sql      # ~11 min
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/04_queries.sql   # ~1 min
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/05_indexes.sql   # ejecutar dos veces
```
Volumen (enero 2025 – octubre 2026): 50 mil clientes, 225 mil cuentas, 1,1 millones de tasas,
2 millones de cotizaciones, 918 mil operaciones, 959 mil comprobantes y 3,5 millones de
registros de historial (1,6 GB). `--escala 0.02` genera una versión pequeña para pruebas.
La semilla es fija: los datos y los resultados de los informes son siempre los mismos.

`grupo_01/datos/completo/etiquetas_anomalias.csv` indica qué clientes tienen comportamiento
inusual inyectado (fraccionamiento, picos, multicuenta, actividad nocturna). Solo se usa para
validar las features; no forma parte del modelo.
