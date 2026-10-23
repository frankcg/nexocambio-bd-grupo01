# NexoCambio — Proyecto de Base de Datos (Grupo 1)

Caso de negocio: casa de cambio digital de divisas y criptoactivos (NexoCambio), el mismo del
curso de Cloud Computing. Autorizado por el docente, con datos sintéticos.

## Entregables (`grupo_01/`)
| Parte | Archivo | Contenido |
|---|---|---|
| 1 | `informe.pdf` | Análisis de negocio, modelo ER, implementación, 10 consultas, 8 features, optimización |
| 1 | `modelo_ER.pdf` | Diagrama ER completo, cardinalidades y diccionario de datos |
| 1 | `sql/01_schema.sql` … `05_indexes.sql` | Esquema, tablas, carga, consultas e índices |
| 1 | `datos/dataset.csv` | Muestra plana de ~10 mil operaciones |
| 2 | `informe_final.pdf` | Caso de IA (detección de operaciones inusuales), caracterización, tecnología, comparación, Polyglot Persistence |
| 2 | `arquitectura.pdf` | Diagrama de arquitectura, flujos, secuencia de scoring y latencia |
| 2 | `modelo_nosql.pdf` | Modelo de datos en Redis, eventos de Kinesis y dimensionamiento |

## Estructura del repositorio
- `grupo_01/`: entregable final (lo que se sube).
- `docs/fuentes/`: fuentes Markdown de los PDF (`python generador/generar_pdfs.py` los regenera).
- `docs/resultados/`: salidas completas de `04_queries.sql` y `05_indexes.sql`.
- `generador/`: generador de datos sintéticos y de PDF (solo biblioteca estándar de Python).
- `pruebas/`: comprueba que cada restricción rechaza los datos inválidos (29 casos, con ROLLBACK).

## Ejecución
PostgreSQL 18 local en el puerto 5433. La contraseña va en `%APPDATA%\postgresql\pgpass.conf`,
nunca en el repositorio.
```
psql -h localhost -p 5433 -U postgres -d postgres -c "CREATE DATABASE nexocambio ENCODING 'UTF8' TEMPLATE template0;"
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/01_schema.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/02_tables.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f pruebas/pruebas_restricciones.sql

python generador/generar_datos.py          # ~5 min; CSV en grupo_01/datos/completo/ (no se versionan)
cd grupo_01
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

## Pendiente antes de entregar
- Completar los integrantes en la portada de `docs/fuentes/informe.md` e `informe_final.md`
  y regenerar los PDF con `python generador/generar_pdfs.py`.
