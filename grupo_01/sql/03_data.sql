-- =============================================================================
-- NexoCambio · 03_data.sql
-- Carga de datos: catálogos con INSERT INTO y datos sintéticos con \copy.
--
-- Requisitos:
--   1. Generar los CSV:  python generador/generar_datos.py
--   2. Ejecutar DESDE la carpeta grupo_01 (las rutas de \copy son relativas):
--        cd grupo_01
--        psql -h localhost -p 5433 -U postgres -d nexocambio -f sql/03_data.sql
--
-- Los CSV no traen los IDs: las tablas usan GENERATED ALWAYS AS IDENTITY y COPY los
-- asigna en el orden de las filas. Por eso se vacían las tablas con RESTART IDENTITY
-- y, al final, se verifica que cada tabla tenga IDs consecutivos desde 1.
-- =============================================================================
\set ON_ERROR_STOP on
\timing on
SET search_path TO nexocambio;

BEGIN;

TRUNCATE historial_estado, comprobante, operacion, usuario_backoffice, cotizacion, tasa_referencial,
         cuenta_cliente, representante_legal, empresa, persona_natural, cliente,
         moneda_red, red_blockchain, banco, moneda
RESTART IDENTITY;

-- -----------------------------------------------------------------------------
-- Catálogos (INSERT INTO). El orden fija los IDs que usa el generador.
-- -----------------------------------------------------------------------------
INSERT INTO moneda (codigo, nombre, tipo, decimales) VALUES
    ('PEN',  'Sol peruano',          'fiat',   2),
    ('USD',  'Dólar estadounidense', 'fiat',   2),
    ('EUR',  'Euro',                 'fiat',   2),
    ('USDT', 'Tether',               'cripto', 2),
    ('USDC', 'USD Coin',             'cripto', 2),
    ('BTC',  'Bitcoin',              'cripto', 6),
    ('ETH',  'Ether',                'cripto', 5);

INSERT INTO banco (nombre) VALUES                       -- id_banco
    ('BCP'), ('Interbank'), ('BBVA'),                    -- 1, 2, 3
    ('Scotiabank'), ('BanBif'), ('Banco Pichincha');     -- 4, 5, 6

INSERT INTO red_blockchain (nombre) VALUES              -- id_red
    ('TRON (TRC20)'), ('Ethereum (ERC20)'),              -- 1, 2
    ('Solana'), ('Bitcoin');                             -- 3, 4

INSERT INTO moneda_red (codigo_moneda, id_red) VALUES
    ('USDT', 1), ('USDT', 2),
    ('USDC', 2), ('USDC', 3),
    ('BTC',  4),
    ('ETH',  2);

INSERT INTO usuario_backoffice (nombre, correo, rol, fecha_alta) VALUES   -- id_usuario
    ('Karla Medina Torres',     'karla.medina@nexocambio.pe',     'analista',   '2024-12-01 09:00-05'),  -- 1
    ('Óscar Salazar Ríos',      'oscar.salazar@nexocambio.pe',    'analista',   '2024-12-01 09:00-05'),  -- 2
    ('Lucía Paredes Cruz',      'lucia.paredes@nexocambio.pe',    'analista',   '2024-12-01 09:00-05'),  -- 3
    ('Marco Aguilar León',      'marco.aguilar@nexocambio.pe',    'analista',   '2024-12-01 09:00-05'),  -- 4
    ('Rosa Huamán Castro',      'rosa.huaman@nexocambio.pe',      'analista',   '2025-02-03 09:00-05'),  -- 5
    ('Daniel Ponce Silva',      'daniel.ponce@nexocambio.pe',     'analista',   '2025-02-03 09:00-05'),  -- 6
    ('Valeria Navarro Ramos',   'valeria.navarro@nexocambio.pe',  'analista',   '2025-04-01 09:00-05'),  -- 7
    ('Jorge Cáceres Vargas',    'jorge.caceres@nexocambio.pe',    'analista',   '2025-04-01 09:00-05'),  -- 8
    ('Milagros Zapata Díaz',    'milagros.zapata@nexocambio.pe',  'analista',   '2025-07-01 09:00-05'),  -- 9
    ('Renzo Córdova Flores',    'renzo.cordova@nexocambio.pe',    'analista',   '2025-07-01 09:00-05'),  -- 10
    ('Patricia Valdivia Rojas', 'patricia.valdivia@nexocambio.pe','supervisor', '2024-12-01 09:00-05'),  -- 11
    ('Gustavo Herrera Mendoza', 'gustavo.herrera@nexocambio.pe',  'supervisor', '2024-12-01 09:00-05');  -- 12

-- -----------------------------------------------------------------------------
-- Datos sintéticos (\copy), en orden de dependencias de las FK.
-- -----------------------------------------------------------------------------
\echo 'Cargando tasa_referencial...'
\copy tasa_referencial (codigo_moneda, fecha_hora, precio_usd, fuente) FROM 'datos/completo/tasa_referencial.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando clientes...'
\copy cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash, fecha_registro) FROM 'datos/completo/cliente.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy persona_natural (id_cliente, nombres, apellidos, fecha_nacimiento, ocupacion, es_pep) FROM 'datos/completo/persona_natural.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy empresa (id_cliente, razon_social, actividad) FROM 'datos/completo/empresa.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\copy representante_legal (id_cliente, nombre, tipo_documento, numero_documento, cargo, vigente, fecha_registro) FROM 'datos/completo/representante_legal.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando cuentas...'
\copy cuenta_cliente (id_cliente, codigo_moneda, tipo, id_banco, tipo_cuenta, numero_cuenta, titular, id_red, direccion_wallet, fecha_registro) FROM 'datos/completo/cuenta_cliente.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando cotizaciones...'
\copy cotizacion (id_cliente, modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino, spread_aplicado, tasa_preferencial, fuente_tasas, fecha_cotizacion, fecha_expiracion) FROM 'datos/completo/cotizacion.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando operaciones...'
\copy operacion (codigo_operacion, id_cotizacion, id_cliente, id_cuenta_origen, id_cuenta_destino, estado_actual, numero_transferencia, motivo_rechazo, fecha_operacion, fecha_actualizacion) FROM 'datos/completo/operacion.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando comprobantes...'
\copy comprobante (id_operacion, nombre_archivo, content_type, tamano_bytes, ruta_s3, fecha_subida) FROM 'datos/completo/comprobante.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')
\echo 'Cargando historial de estados...'
\copy historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario, comentario, fecha_cambio) FROM 'datos/completo/historial_estado.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')

-- -----------------------------------------------------------------------------
-- Verificaciones: si alguna falla, se revierte toda la carga.
-- -----------------------------------------------------------------------------
DO $$
DECLARE
    t RECORD;
    n BIGINT;
    maximo BIGINT;
BEGIN
    -- 1. IDs consecutivos desde 1 (los CSV referencian IDs por posición).
    FOR t IN SELECT * FROM (VALUES ('cliente', 'id_cliente'), ('representante_legal', 'id_representante'),
                                   ('cuenta_cliente', 'id_cuenta'), ('tasa_referencial', 'id_tasa'),
                                   ('cotizacion', 'id_cotizacion'), ('operacion', 'id_operacion'),
                                   ('comprobante', 'id_comprobante'), ('historial_estado', 'id_historial'))
                           AS v(tabla, columna)
    LOOP
        EXECUTE format('SELECT count(*), coalesce(max(%I), 0) FROM %I', t.columna, t.tabla) INTO n, maximo;
        IF n <> maximo THEN
            RAISE EXCEPTION 'IDs no consecutivos en %: % filas, id máximo %', t.tabla, n, maximo;
        END IF;
    END LOOP;

    -- 2. Cada cliente es exactamente persona o empresa.
    SELECT count(*) INTO n FROM cliente c
    WHERE (SELECT count(*) FROM persona_natural p WHERE p.id_cliente = c.id_cliente)
        + (SELECT count(*) FROM empresa e WHERE e.id_cliente = c.id_cliente) <> 1;
    IF n > 0 THEN RAISE EXCEPTION '% clientes sin subtipo', n; END IF;

    -- 3. El estado_actual (desnormalizado) coincide con el último registro del historial.
    SELECT count(*) INTO n
    FROM operacion o
    JOIN (SELECT DISTINCT ON (id_operacion) id_operacion, estado_nuevo
          FROM historial_estado ORDER BY id_operacion, fecha_cambio DESC) u USING (id_operacion)
    WHERE u.estado_nuevo <> o.estado_actual;
    IF n > 0 THEN RAISE EXCEPTION '% operaciones con estado_actual inconsistente', n; END IF;

    RAISE NOTICE 'Verificaciones correctas.';
END $$;

COMMIT;

ANALYZE;

SELECT 'cliente' AS tabla, count(*) AS filas FROM cliente
UNION ALL SELECT 'persona_natural', count(*) FROM persona_natural
UNION ALL SELECT 'empresa', count(*) FROM empresa
UNION ALL SELECT 'representante_legal', count(*) FROM representante_legal
UNION ALL SELECT 'cuenta_cliente', count(*) FROM cuenta_cliente
UNION ALL SELECT 'tasa_referencial', count(*) FROM tasa_referencial
UNION ALL SELECT 'cotizacion', count(*) FROM cotizacion
UNION ALL SELECT 'operacion', count(*) FROM operacion
UNION ALL SELECT 'comprobante', count(*) FROM comprobante
UNION ALL SELECT 'historial_estado', count(*) FROM historial_estado;
