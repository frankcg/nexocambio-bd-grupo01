# NexoCambio — Proyecto de Base de Datos (Grupo 1)

Caso de negocio: casa de cambio digital de divisas y criptoactivos (NexoCambio).
Modelo relacional en PostgreSQL 18 con datos sintéticos.

## Estructura
- `docs/`: borradores del informe (análisis de negocio, modelo ER).
- `grupo_01/`: entregable final.
  - `sql/01_schema.sql` … `05_indexes.sql`
  - `datos/dataset.csv`: muestra de los datos generados.
- `generador/`: script Python que genera los datos sintéticos completos.

## Ejecución
```
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/01_schema.sql
psql -h localhost -p 5433 -U postgres -d nexocambio -f grupo_01/sql/02_tables.sql
```
