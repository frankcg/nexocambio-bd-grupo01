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
- **Parte 2 (entregable 2): borrador** en `entrega_2/` (fuentes en `docs/fuentes/parte2/`).
  Caso de IA: detección de operaciones inusuales en tiempo real (prevención de lavado de
  activos). Tecnología: Redis como feature store en línea, Kinesis (CDC desde PostgreSQL) y
  Data Lake S3. Falta revisarlo contra el enunciado y regenerar sus PDF.

## Pendientes (al 14/11/2026)
- Enunciado de la Parte 1 en `docs/enunciados/parte1.md`. El informe cubre todos sus puntos
  (revisado el 14/11/2026). Falta el enunciado de la Parte 2.
- **Subir a GitHub** (lo pide el equipo): crear el repositorio y hacer push. El repo aún **no
  tiene remoto**. `gh` está autenticado como `frankcg` (keyring), pero la variable `GITHUB_TOKEN`
  tiene un token inválido que lo bloquea: quitarla o ejecutar `gh` sin ella. `datos/completo/`
  queda fuera (`*.csv` ya está en `.gitignore`; GitHub rechaza archivos de más de 100 MB).
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
- `entrega_2/`: PDF del borrador de la Parte 2 (`informe_final`, `modelo_nosql`, `arquitectura`).
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
- Features en PostgreSQL (para la Parte 2): 5,6 ms un cliente típico, 100 ms el cliente con
  más historial (CLI-ZYCHEZ, 2 809 operaciones), 3,6 s todos los clientes.
