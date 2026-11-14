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
  Lake S3. Revisada contra el enunciado el 14/11/2026: cubre todo. Kafka reemplazó a Kinesis
  (el profesor enseña Kafka / Confluent Cloud en clase).
- **Presentación final** (máx. ≈ 11 diapositivas, con demo). Demo propuesta: seguir a
  CLI-ZYCHEZ. Acto 1 en PostgreSQL (restricción que rechaza, C6, features, O1 antes/después).
  Acto 2: evento en un topic de Confluent Cloud → consumidor → Redis en Docker (< 1 ms frente a
  257 ms en PostgreSQL). Falta: cuenta de Confluent Cloud (cluster y API keys los crea el equipo),
  script de la demo y guion de diapositivas.

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
