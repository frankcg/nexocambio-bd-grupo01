# NexoCambio — Proyecto de Base de Datos (Grupo 1)

Caso de negocio: casa de cambio digital de divisas y criptoactivos (NexoCambio).
Modelo relacional en PostgreSQL 18 con datos sintéticos.

## Estructura
- `docs/`: borradores del informe (análisis de negocio, modelo ER).
- `grupo_01/`: entregable final.
  - `sql/01_schema.sql` … `05_indexes.sql`
  - `datos/dataset.csv`: muestra de los datos generados.
- `generador/`: script Python que genera los datos sintéticos completos.
- `pruebas/`: comprueba que cada restricción rechaza los datos inválidos (con ROLLBACK).

## Ejecución
PostgreSQL 18 local en el puerto 5433. La contraseña va en `%APPDATA%\postgresql\pgpass.conf`,
nunca en el repositorio.
```
psql -h localhost -p 5433 -U postgres -d postgres -c "CREATE DATABASE nexocambio ENCODING 'UTF8' TEMPLATE template0;"
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/01_schema.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/02_tables.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f pruebas/pruebas_restricciones.sql
```

### Datos sintéticos
```
python generador/generar_datos.py          # ~5 min; CSV en grupo_01/datos/completo/ (no se versionan)
cd grupo_01
psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/03_data.sql   # ~10 min
```
Volumen (enero 2025 – octubre 2026): 50 mil clientes, 225 mil cuentas, 1,1 millones de tasas,
2 millones de cotizaciones, 918 mil operaciones, 959 mil comprobantes y 3,5 millones de
registros de historial. `python generador/generar_datos.py --escala 0.02` genera una versión
pequeña para pruebas. La semilla es fija: los datos son siempre los mismos.

`grupo_01/datos/dataset.csv` es una muestra plana (~1 % de las operaciones) para el entregable.
`grupo_01/datos/completo/etiquetas_anomalias.csv` indica qué clientes tienen comportamiento
inusual inyectado (fraccionamiento, picos, multicuenta, actividad nocturna) para la Parte 2.
