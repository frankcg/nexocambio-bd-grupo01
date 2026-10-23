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
