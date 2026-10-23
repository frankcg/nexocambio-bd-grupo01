-- =============================================================================
-- NexoCambio · Pruebas de restricciones
-- Inserta un caso válido y comprueba que cada regla de negocio rechaza los datos
-- inválidos. Todo corre en una transacción con ROLLBACK: no deja datos y puede
-- ejecutarse con la base vacía o con los datos ya cargados.
--   psql -h localhost -p 5433 -U postgres -d nexocambio -f pruebas/pruebas_restricciones.sql
-- =============================================================================
\set ON_ERROR_STOP on
\set QUIET on
SET search_path TO nexocambio;
BEGIN;

-- Ejecuta una sentencia que DEBE fallar; si no falla, aborta las pruebas.
CREATE FUNCTION pg_temp.debe_fallar(descripcion TEXT, sentencia TEXT) RETURNS VOID AS $$
BEGIN
    BEGIN
        EXECUTE sentencia;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'OK  %  ->  %', rpad(descripcion, 48), SQLERRM;
        RETURN;
    END;
    RAISE EXCEPTION 'FALLO: se aceptó un dato inválido: %', descripcion;
END $$ LANGUAGE plpgsql;

-- IDs de los datos de prueba: se buscan por clave de negocio (no se asume que empiecen en 1).
CREATE FUNCTION pg_temp.id(clave TEXT) RETURNS BIGINT AS $$
    SELECT current_setting('prueba.' || clave)::BIGINT
$$ LANGUAGE sql;

CREATE FUNCTION pg_temp.guardar(clave TEXT, valor BIGINT) RETURNS VOID AS $$
    SELECT set_config('prueba.' || clave, valor::TEXT, true)
$$ LANGUAGE sql;

-- ----------------------------------------------------------- datos válidos
-- Los catálogos pueden existir ya si la base tiene datos cargados.
INSERT INTO moneda VALUES ('PEN', 'Sol peruano', 'fiat', 2), ('USD', 'Dólar estadounidense', 'fiat', 2),
                          ('USDT', 'Tether', 'cripto', 2), ('BTC', 'Bitcoin', 'cripto', 6)
ON CONFLICT DO NOTHING;
INSERT INTO banco (nombre) VALUES ('BCP'), ('Interbank') ON CONFLICT DO NOTHING;
INSERT INTO red_blockchain (nombre) VALUES ('TRON (TRC20)'), ('Bitcoin') ON CONFLICT DO NOTHING;
INSERT INTO moneda_red SELECT 'USDT', id_red FROM red_blockchain WHERE nombre = 'TRON (TRC20)' ON CONFLICT DO NOTHING;
INSERT INTO moneda_red SELECT 'BTC',  id_red FROM red_blockchain WHERE nombre = 'Bitcoin'      ON CONFLICT DO NOTHING;

INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
VALUES ('CLI-TEST01', 'persona', 'DNI', '00000001',    'ana.prueba@correo.pe',  '987654321', 'hash'),
       ('CLI-TEST02', 'empresa', 'RUC', '20000000001', 'acme.prueba@correo.pe', '912345678', 'hash');
INSERT INTO usuario_backoffice (nombre, correo, rol)
VALUES ('Analista Prueba', 'analista.prueba@nexocambio.pe', 'analista');

DO $$ BEGIN PERFORM pg_temp.guardar('ana',       (SELECT id_cliente FROM cliente WHERE codigo_cliente = 'CLI-TEST01')),
       pg_temp.guardar('acme',      (SELECT id_cliente FROM cliente WHERE codigo_cliente = 'CLI-TEST02')),
       pg_temp.guardar('bcp',       (SELECT id_banco FROM banco WHERE nombre = 'BCP')),
       pg_temp.guardar('interbank', (SELECT id_banco FROM banco WHERE nombre = 'Interbank')),
       pg_temp.guardar('red_btc',   (SELECT id_red FROM red_blockchain WHERE nombre = 'Bitcoin')),
       pg_temp.guardar('analista',  (SELECT id_usuario FROM usuario_backoffice
                                     WHERE correo = 'analista.prueba@nexocambio.pe')); END $$;

INSERT INTO persona_natural (id_cliente, nombres, apellidos, fecha_nacimiento)
VALUES (pg_temp.id('ana'), 'Ana', 'Pérez', '1990-05-10');
INSERT INTO empresa (id_cliente, razon_social, actividad) VALUES (pg_temp.id('acme'), 'Acme SAC', 'Comercio');

INSERT INTO cuenta_cliente (id_cliente, codigo_moneda, tipo, id_banco, tipo_cuenta, numero_cuenta, titular)
VALUES (pg_temp.id('ana'),  'USD', 'banco', pg_temp.id('bcp'),       'Ahorros',   '00000000000001', 'Ana Pérez'),
       (pg_temp.id('ana'),  'PEN', 'banco', pg_temp.id('bcp'),       'Ahorros',   '00000000000002', 'Ana Pérez'),
       (pg_temp.id('acme'), 'PEN', 'banco', pg_temp.id('interbank'), 'Corriente', '00000000000003', 'Acme SAC');

INSERT INTO cotizacion (id_cliente, modalidad, moneda_origen, moneda_destino, monto_origen, tasa,
                        monto_destino, spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
VALUES (pg_temp.id('ana'), 'casa', 'USD', 'PEN', 1000, 3.7350000000, 3735.00, 0.0045, 'en_vivo',
        '2026-10-01 10:00-05', '2026-10-01 10:05-05');

DO $$ BEGIN PERFORM pg_temp.guardar('cta_usd',  (SELECT id_cuenta FROM cuenta_cliente WHERE numero_cuenta = '00000000000001')),
       pg_temp.guardar('cta_pen',  (SELECT id_cuenta FROM cuenta_cliente WHERE numero_cuenta = '00000000000002')),
       pg_temp.guardar('cta_acme', (SELECT id_cuenta FROM cuenta_cliente WHERE numero_cuenta = '00000000000003')),
       pg_temp.guardar('cot',      (SELECT max(id_cotizacion) FROM cotizacion WHERE id_cliente = pg_temp.id('ana'))); END $$;

INSERT INTO operacion (codigo_operacion, id_cotizacion, id_cliente, id_cuenta_origen, id_cuenta_destino,
                       fecha_operacion, fecha_actualizacion)
VALUES ('NX-TEST0001', pg_temp.id('cot'), pg_temp.id('ana'), pg_temp.id('cta_usd'), pg_temp.id('cta_pen'),
        '2026-10-01 10:01-05', '2026-10-01 10:01-05');
DO $$ BEGIN PERFORM pg_temp.guardar('op', (SELECT id_operacion FROM operacion WHERE codigo_operacion = 'NX-TEST0001')); END $$;

INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario, fecha_cambio)
VALUES (pg_temp.id('op'), NULL,                       'Pendiente de comprobante', NULL,                   '2026-10-01 10:01-05'),
       (pg_temp.id('op'), 'Pendiente de comprobante', 'Pendiente de validación',  NULL,                   '2026-10-01 10:03-05'),
       (pg_temp.id('op'), 'Pendiente de validación',  'En proceso',               pg_temp.id('analista'), '2026-10-01 10:20-05'),
       (pg_temp.id('op'), 'En proceso',               'Procesada',                pg_temp.id('analista'), '2026-10-01 10:40-05');

\echo 'Datos válidos insertados. Probando restricciones...'
DO $pruebas$ BEGIN

-- --------------------------------------------------------------- clientes
PERFORM pg_temp.debe_fallar('Correo duplicado',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '00000002', 'ana.prueba@correo.pe', '987654321', 'h')$q$);
PERFORM pg_temp.debe_fallar('Documento duplicado',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '00000001', 'otra.prueba@correo.pe', '987654321', 'h')$q$);
PERFORM pg_temp.debe_fallar('Correo con mayúsculas',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '00000002', 'Otra.Prueba@Correo.pe', '987654321', 'h')$q$);
PERFORM pg_temp.debe_fallar('Celular que no empieza con 9',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '00000002', 'otra.prueba@correo.pe', '812345678', 'h')$q$);
PERFORM pg_temp.debe_fallar('DNI con 7 dígitos',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '0000002', 'otra.prueba@correo.pe', '987654321', 'h')$q$);
PERFORM pg_temp.debe_fallar('Empresa registrada con DNI',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'empresa', 'DNI', '00000002', 'otra.prueba@correo.pe', '987654321', 'h')$q$);
PERFORM pg_temp.debe_fallar('Persona menor de edad',
  $q$INSERT INTO cliente (codigo_cliente, tipo_cliente, tipo_documento, numero_documento, correo, telefono, password_hash)
     VALUES ('CLI-TEST03', 'persona', 'DNI', '00000002', 'otra.prueba@correo.pe', '987654321', 'h');
     INSERT INTO persona_natural (id_cliente, nombres, apellidos, fecha_nacimiento)
     VALUES (currval(pg_get_serial_sequence('cliente', 'id_cliente')), 'Leo', 'Ruiz', current_date - 3000)$q$);
PERFORM pg_temp.debe_fallar('Empresa cargada como persona natural',
  $q$INSERT INTO persona_natural (id_cliente, nombres, apellidos, fecha_nacimiento)
     VALUES (pg_temp.id('acme'), 'X', 'Y', '1980-01-01')$q$);
PERFORM pg_temp.debe_fallar('Persona cargada como empresa',
  $q$INSERT INTO empresa (id_cliente, razon_social) VALUES (pg_temp.id('ana'), 'Ana SAC')$q$);
PERFORM pg_temp.debe_fallar('Representante de una persona natural',
  $q$INSERT INTO representante_legal (id_cliente, nombre, tipo_documento, numero_documento, cargo)
     VALUES (pg_temp.id('ana'), 'Juan', 'DNI', '00000009', 'Gerente')$q$);

-- ----------------------------------------------------------------- cuentas
PERFORM pg_temp.debe_fallar('Cuenta bancaria sin número',
  $q$INSERT INTO cuenta_cliente (id_cliente, codigo_moneda, tipo, id_banco, tipo_cuenta, titular)
     VALUES (pg_temp.id('ana'), 'PEN', 'banco', pg_temp.id('bcp'), 'Ahorros', 'Ana')$q$);
PERFORM pg_temp.debe_fallar('Cuenta bancaria con red blockchain',
  $q$INSERT INTO cuenta_cliente (id_cliente, codigo_moneda, tipo, id_banco, tipo_cuenta, numero_cuenta, titular, id_red)
     VALUES (pg_temp.id('ana'), 'PEN', 'banco', pg_temp.id('bcp'), 'Ahorros', '0000000000009', 'Ana', pg_temp.id('red_btc'))$q$);
PERFORM pg_temp.debe_fallar('Wallet USDT en la red Bitcoin (N:M)',
  $q$INSERT INTO cuenta_cliente (id_cliente, codigo_moneda, tipo, id_red, direccion_wallet)
     VALUES (pg_temp.id('ana'), 'USDT', 'wallet', pg_temp.id('red_btc'), 'TXyz1234567890abcdefghijklmnop')$q$);
PERFORM pg_temp.debe_fallar('Número de cuenta con letras',
  $q$INSERT INTO cuenta_cliente (id_cliente, codigo_moneda, tipo, id_banco, tipo_cuenta, numero_cuenta, titular)
     VALUES (pg_temp.id('ana'), 'PEN', 'banco', pg_temp.id('bcp'), 'Ahorros', '19A12345678', 'Ana')$q$);

-- ------------------------------------------------------------- cotizaciones
PERFORM pg_temp.debe_fallar('Cotización con la misma moneda',
  $q$INSERT INTO cotizacion (modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino,
                             spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
     VALUES ('casa', 'USD', 'USD', 100, 1, 100, 0, 'en_vivo', now(), now() + interval '5 min')$q$);
PERFORM pg_temp.debe_fallar('Cotización con monto negativo',
  $q$INSERT INTO cotizacion (modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino,
                             spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
     VALUES ('casa', 'USD', 'PEN', -100, 3.7, 370, 0.0045, 'en_vivo', now(), now() + interval '5 min')$q$);
PERFORM pg_temp.debe_fallar('Monto destino que no cuadra con la tasa',
  $q$INSERT INTO cotizacion (modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino,
                             spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
     VALUES ('casa', 'USD', 'PEN', 100, 3.7, 380, 0.0045, 'en_vivo', now(), now() + interval '5 min')$q$);
PERFORM pg_temp.debe_fallar('Cotización que vence antes de emitirse',
  $q$INSERT INTO cotizacion (modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino,
                             spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
     VALUES ('casa', 'USD', 'PEN', 100, 3.7, 370, 0.0045, 'en_vivo', now(), now() - interval '5 min')$q$);

-- -------------------------------------------------------------- operaciones
PERFORM pg_temp.debe_fallar('Cotización usada en dos operaciones',
  $q$INSERT INTO operacion (codigo_operacion, id_cotizacion, id_cliente, id_cuenta_origen, id_cuenta_destino)
     VALUES ('NX-TEST0002', pg_temp.id('cot'), pg_temp.id('ana'), pg_temp.id('cta_usd'), pg_temp.id('cta_pen'))$q$);
PERFORM pg_temp.debe_fallar('Operación con la cuenta de otro cliente',
  $q$INSERT INTO cotizacion (modalidad, moneda_origen, moneda_destino, monto_origen, tasa, monto_destino,
                             spread_aplicado, fuente_tasas, fecha_cotizacion, fecha_expiracion)
     VALUES ('casa', 'USD', 'PEN', 100, 3.7, 370, 0.0045, 'en_vivo', now(), now() + interval '5 min');
     INSERT INTO operacion (codigo_operacion, id_cotizacion, id_cliente, id_cuenta_origen, id_cuenta_destino)
     VALUES ('NX-TEST0002', currval(pg_get_serial_sequence('cotizacion', 'id_cotizacion')),
             pg_temp.id('ana'), pg_temp.id('cta_usd'), pg_temp.id('cta_acme'))$q$);
PERFORM pg_temp.debe_fallar('Rechazada sin motivo',
  $q$UPDATE operacion SET estado_actual = 'Rechazada' WHERE id_operacion = pg_temp.id('op')$q$);
PERFORM pg_temp.debe_fallar('Estado inexistente',
  $q$UPDATE operacion SET estado_actual = 'Anulada' WHERE id_operacion = pg_temp.id('op')$q$);
PERFORM pg_temp.debe_fallar('Comprobante de más de 4 MB',
  $q$INSERT INTO comprobante (id_operacion, nombre_archivo, content_type, tamano_bytes, ruta_s3)
     VALUES (pg_temp.id('op'), 'voucher.pdf', 'application/pdf', 5000000, 's3://bucket/prueba.pdf')$q$);
PERFORM pg_temp.debe_fallar('Comprobante en formato no permitido',
  $q$INSERT INTO comprobante (id_operacion, nombre_archivo, content_type, tamano_bytes, ruta_s3)
     VALUES (pg_temp.id('op'), 'voucher.gif', 'image/gif', 1000, 's3://bucket/prueba.gif')$q$);

-- ----------------------------------------------------- máquina de estados
PERFORM pg_temp.debe_fallar('Transición Procesada -> En proceso',
  $q$INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario)
     VALUES (pg_temp.id('op'), 'Procesada', 'En proceso', pg_temp.id('analista'))$q$);
PERFORM pg_temp.debe_fallar('Saltar de Pendiente de comprobante a Procesada',
  $q$INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario)
     VALUES (pg_temp.id('op'), 'Pendiente de comprobante', 'Procesada', pg_temp.id('analista'))$q$);
PERFORM pg_temp.debe_fallar('Primer registro distinto del inicial',
  $q$INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario)
     VALUES (pg_temp.id('op'), NULL, 'Procesada', pg_temp.id('analista'))$q$);
PERFORM pg_temp.debe_fallar('Decisión de validación sin usuario',
  $q$INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo)
     VALUES (pg_temp.id('op'), 'Pendiente de validación', 'Rechazada')$q$);
PERFORM pg_temp.debe_fallar('Mismo estado alcanzado dos veces',
  $q$INSERT INTO historial_estado (id_operacion, estado_anterior, estado_nuevo, id_usuario)
     VALUES (pg_temp.id('op'), 'En proceso', 'Procesada', pg_temp.id('analista'))$q$);

END $pruebas$;
\echo 'Todas las restricciones rechazaron los datos inválidos.'
ROLLBACK;
