-- =============================================================================
-- NexoCambio · 02_tables.sql
-- Tablas, claves y restricciones del modelo relacional (15 entidades, 3FN).
-- Orden: catálogos → clientes → cuentas → tasas y cotizaciones → operaciones.
-- =============================================================================

SET search_path TO nexocambio;

-- -----------------------------------------------------------------------------
-- Catálogos
-- -----------------------------------------------------------------------------
CREATE TABLE moneda (
    codigo      VARCHAR(5)   PRIMARY KEY CHECK (codigo ~ '^[A-Z]{3,5}$'),
    nombre      VARCHAR(40)  NOT NULL UNIQUE,
    tipo        VARCHAR(6)   NOT NULL CHECK (tipo IN ('fiat', 'cripto')),
    decimales   SMALLINT     NOT NULL CHECK (decimales BETWEEN 0 AND 8)
);
COMMENT ON TABLE moneda IS 'Divisas (fiat) y criptoactivos que opera la casa de cambio.';

CREATE TABLE banco (
    id_banco    SMALLINT     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      VARCHAR(40)  NOT NULL UNIQUE
);

CREATE TABLE red_blockchain (
    id_red      SMALLINT     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      VARCHAR(40)  NOT NULL UNIQUE
);

-- Resuelve la relación N:M moneda–red (USDT viaja por TRC20 y ERC20; ERC20 lleva USDT, USDC y ETH).
CREATE TABLE moneda_red (
    codigo_moneda VARCHAR(5) NOT NULL REFERENCES moneda (codigo),
    id_red        SMALLINT   NOT NULL REFERENCES red_blockchain (id_red),
    PRIMARY KEY (codigo_moneda, id_red)
);
COMMENT ON TABLE moneda_red IS 'Redes blockchain admitidas por cada criptoactivo (asociativa N:M).';

-- -----------------------------------------------------------------------------
-- Clientes: supertipo cliente con subtipos excluyentes persona_natural / empresa
-- -----------------------------------------------------------------------------
CREATE TABLE cliente (
    id_cliente        BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_cliente    VARCHAR(10)   NOT NULL UNIQUE CHECK (codigo_cliente ~ '^CLI-[A-Z0-9]{6}$'),
    tipo_cliente      VARCHAR(7)    NOT NULL CHECK (tipo_cliente IN ('persona', 'empresa')),
    tipo_documento    VARCHAR(9)    NOT NULL CHECK (tipo_documento IN ('DNI', 'CE', 'Pasaporte', 'RUC')),
    numero_documento  VARCHAR(12)   NOT NULL,
    correo            VARCHAR(120)  NOT NULL UNIQUE,
    telefono          CHAR(9)       NOT NULL CHECK (telefono ~ '^9[0-9]{8}$'),
    password_hash     VARCHAR(255)  NOT NULL,
    fecha_registro    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_cliente_documento UNIQUE (tipo_documento, numero_documento),
    -- Destino de la FK compuesta de los subtipos.
    CONSTRAINT uq_cliente_tipo UNIQUE (id_cliente, tipo_cliente),
    CONSTRAINT ck_cliente_correo CHECK (correo = lower(correo) AND correo ~ '^[^\s@]+@[^\s@]+\.[^\s@]{2,}$'),
    -- Las empresas se registran con RUC; las personas, con DNI, CE o pasaporte.
    CONSTRAINT ck_cliente_documento_tipo CHECK ((tipo_cliente = 'empresa') = (tipo_documento = 'RUC')),
    CONSTRAINT ck_cliente_documento_formato CHECK (
           (tipo_documento = 'DNI'       AND numero_documento ~ '^[0-9]{8}$')
        OR (tipo_documento = 'CE'        AND numero_documento ~ '^[A-Za-z0-9]{9,12}$')
        OR (tipo_documento = 'Pasaporte' AND numero_documento ~ '^[A-Za-z0-9]{6,12}$')
        OR (tipo_documento = 'RUC'       AND numero_documento ~ '^(10|15|17|20)[0-9]{9}$'))
);
COMMENT ON TABLE cliente IS 'Supertipo: datos comunes de personas naturales y empresas.';

CREATE TABLE persona_natural (
    id_cliente        BIGINT        PRIMARY KEY,
    tipo_cliente      VARCHAR(7)    NOT NULL DEFAULT 'persona' CHECK (tipo_cliente = 'persona'),
    nombres           VARCHAR(100)  NOT NULL,
    apellidos         VARCHAR(100)  NOT NULL,
    fecha_nacimiento  DATE          NOT NULL,
    ocupacion         VARCHAR(13)   CHECK (ocupacion IN ('Dependiente', 'Independiente', 'Empresario',
                                                         'Estudiante', 'Jubilado', 'Otro')),
    es_pep            BOOLEAN       NOT NULL DEFAULT false,
    -- Solo mayores de edad (se verifica al insertar o modificar la fila).
    CONSTRAINT ck_persona_mayor_edad CHECK (fecha_nacimiento BETWEEN DATE '1900-01-01'
                                                                AND current_date - INTERVAL '18 years'),
    CONSTRAINT fk_persona_cliente FOREIGN KEY (id_cliente, tipo_cliente)
        REFERENCES cliente (id_cliente, tipo_cliente) ON DELETE CASCADE
);
COMMENT ON COLUMN persona_natural.es_pep IS 'Persona Expuesta Políticamente (debida diligencia reforzada).';

CREATE TABLE empresa (
    id_cliente        BIGINT        PRIMARY KEY,
    tipo_cliente      VARCHAR(7)    NOT NULL DEFAULT 'empresa' CHECK (tipo_cliente = 'empresa'),
    razon_social      VARCHAR(150)  NOT NULL,
    actividad         VARCHAR(12)   CHECK (actividad IN ('Comercio', 'Servicios', 'Manufactura',
                                                         'Tecnología', 'Construcción', 'Otro')),
    CONSTRAINT fk_empresa_cliente FOREIGN KEY (id_cliente, tipo_cliente)
        REFERENCES cliente (id_cliente, tipo_cliente) ON DELETE CASCADE
);

CREATE TABLE representante_legal (
    id_representante  BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente        BIGINT        NOT NULL REFERENCES empresa (id_cliente) ON DELETE CASCADE,
    nombre            VARCHAR(150)  NOT NULL,
    tipo_documento    VARCHAR(9)    NOT NULL CHECK (tipo_documento IN ('DNI', 'CE', 'Pasaporte')),
    numero_documento  VARCHAR(12)   NOT NULL,
    cargo             VARCHAR(60)   NOT NULL,
    vigente           BOOLEAN       NOT NULL DEFAULT true,
    fecha_registro    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uq_representante_empresa UNIQUE (id_cliente, tipo_documento, numero_documento)
);

-- -----------------------------------------------------------------------------
-- Cuentas bancarias y billeteras del cliente
-- -----------------------------------------------------------------------------
CREATE TABLE cuenta_cliente (
    id_cuenta         BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cliente        BIGINT        NOT NULL REFERENCES cliente (id_cliente) ON DELETE CASCADE,
    codigo_moneda     VARCHAR(5)    NOT NULL REFERENCES moneda (codigo),
    tipo              VARCHAR(6)    NOT NULL CHECK (tipo IN ('banco', 'wallet')),
    id_banco          SMALLINT      REFERENCES banco (id_banco),
    tipo_cuenta       VARCHAR(9)    CHECK (tipo_cuenta IN ('Ahorros', 'Corriente')),
    numero_cuenta     VARCHAR(20)   CHECK (numero_cuenta ~ '^[0-9]{10,20}$'),
    titular           VARCHAR(150),
    id_red            SMALLINT,
    direccion_wallet  VARCHAR(64)   CHECK (direccion_wallet ~ '^[A-Za-z0-9]{26,64}$'),
    fecha_registro    TIMESTAMPTZ   NOT NULL DEFAULT now(),
    -- Destino de las FK compuestas de operacion: la cuenta debe ser del mismo cliente.
    CONSTRAINT uq_cuenta_cliente UNIQUE (id_cuenta, id_cliente),
    -- La red debe ser válida para el criptoactivo (MATCH SIMPLE: no aplica si id_red es NULL).
    CONSTRAINT fk_cuenta_moneda_red FOREIGN KEY (codigo_moneda, id_red)
        REFERENCES moneda_red (codigo_moneda, id_red),
    CONSTRAINT ck_cuenta_banco_o_wallet CHECK (
           (tipo = 'banco'  AND id_banco IS NOT NULL AND tipo_cuenta IS NOT NULL
                            AND numero_cuenta IS NOT NULL AND titular IS NOT NULL
                            AND id_red IS NULL AND direccion_wallet IS NULL)
        OR (tipo = 'wallet' AND id_red IS NOT NULL AND direccion_wallet IS NOT NULL
                            AND id_banco IS NULL AND tipo_cuenta IS NULL
                            AND numero_cuenta IS NULL AND titular IS NULL)),
    CONSTRAINT uq_cuenta_bancaria UNIQUE (id_cliente, id_banco, numero_cuenta),
    CONSTRAINT uq_cuenta_wallet   UNIQUE (id_cliente, id_red, direccion_wallet)
);
COMMENT ON TABLE cuenta_cliente IS 'Cuentas bancarias (fiat) y billeteras (cripto) que el cliente usa como origen o destino.';

-- -----------------------------------------------------------------------------
-- Tasas de referencia y cotizaciones
-- -----------------------------------------------------------------------------
CREATE TABLE tasa_referencial (
    id_tasa           BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_moneda     VARCHAR(5)    NOT NULL REFERENCES moneda (codigo),
    fecha_hora        TIMESTAMPTZ   NOT NULL,
    precio_usd        NUMERIC(24,8) NOT NULL CHECK (precio_usd > 0),
    fuente            VARCHAR(30)   NOT NULL,
    CONSTRAINT uq_tasa_moneda_fecha UNIQUE (codigo_moneda, fecha_hora)
);
COMMENT ON TABLE tasa_referencial IS 'Serie temporal: precio de mercado en USD de cada moneda.';

CREATE TABLE cotizacion (
    id_cotizacion     BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- NULL = visitante sin cuenta (POST /cotizar es una ruta pública).
    id_cliente        BIGINT         REFERENCES cliente (id_cliente) ON DELETE SET NULL,
    modalidad         VARCHAR(6)     NOT NULL CHECK (modalidad IN ('casa', 'cripto')),
    moneda_origen     VARCHAR(5)     NOT NULL REFERENCES moneda (codigo),
    moneda_destino    VARCHAR(5)     NOT NULL REFERENCES moneda (codigo),
    monto_origen      NUMERIC(24,8)  NOT NULL CHECK (monto_origen > 0),
    -- Unidades de moneda_destino por unidad de moneda_origen, ya con el spread descontado.
    tasa              NUMERIC(20,10) NOT NULL CHECK (tasa > 0),
    monto_destino     NUMERIC(24,8)  NOT NULL CHECK (monto_destino > 0),
    spread_aplicado   NUMERIC(6,5)   NOT NULL CHECK (spread_aplicado >= 0 AND spread_aplicado < 0.1),
    tasa_preferencial BOOLEAN        NOT NULL DEFAULT false,
    fuente_tasas      VARCHAR(11)    NOT NULL CHECK (fuente_tasas IN ('en_vivo', 'cache', 'referencial')),
    fecha_cotizacion  TIMESTAMPTZ    NOT NULL DEFAULT now(),
    fecha_expiracion  TIMESTAMPTZ    NOT NULL,
    CONSTRAINT ck_cotizacion_monedas CHECK (moneda_origen <> moneda_destino),
    CONSTRAINT ck_cotizacion_vigencia CHECK (fecha_expiracion - fecha_cotizacion
                                             BETWEEN INTERVAL '1 minute' AND INTERVAL '30 minutes'),
    -- monto_destino = monto_origen × tasa, redondeado a los decimales de la moneda destino.
    CONSTRAINT ck_cotizacion_calculo CHECK (abs(monto_destino - monto_origen * tasa) <= 0.005)
);
COMMENT ON TABLE cotizacion IS 'Tasa garantizada al cliente por un tiempo limitado (5 minutos por defecto).';

-- -----------------------------------------------------------------------------
-- Back-office, operaciones, comprobantes e historial de estados
-- -----------------------------------------------------------------------------
CREATE TABLE usuario_backoffice (
    id_usuario        BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre            VARCHAR(150)  NOT NULL,
    correo            VARCHAR(120)  NOT NULL UNIQUE CHECK (correo = lower(correo)),
    rol               VARCHAR(10)   NOT NULL CHECK (rol IN ('analista', 'supervisor')),
    activo            BOOLEAN       NOT NULL DEFAULT true,
    fecha_alta        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE operacion (
    id_operacion         BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo_operacion     VARCHAR(11)   NOT NULL UNIQUE CHECK (codigo_operacion ~ '^NX-[A-Z0-9]{8}$'),
    -- UNIQUE: una cotización solo puede concretarse en una operación.
    id_cotizacion        BIGINT        NOT NULL UNIQUE REFERENCES cotizacion (id_cotizacion),
    id_cliente           BIGINT        NOT NULL REFERENCES cliente (id_cliente),
    id_cuenta_origen     BIGINT        NOT NULL,
    id_cuenta_destino    BIGINT        NOT NULL,
    -- Desnormalización controlada: es el último estado de historial_estado.
    estado_actual        VARCHAR(25)   NOT NULL DEFAULT 'Pendiente de comprobante'
                                       CHECK (estado_actual IN ('Pendiente de comprobante', 'Pendiente de validación',
                                                                'En proceso', 'Procesada', 'Rechazada')),
    numero_transferencia VARCHAR(40),
    motivo_rechazo       VARCHAR(300)  CHECK (char_length(motivo_rechazo) >= 3),
    fecha_operacion      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    fecha_actualizacion  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    -- Las cuentas de origen y destino deben pertenecer al cliente de la operación.
    CONSTRAINT fk_operacion_cuenta_origen FOREIGN KEY (id_cuenta_origen, id_cliente)
        REFERENCES cuenta_cliente (id_cuenta, id_cliente),
    CONSTRAINT fk_operacion_cuenta_destino FOREIGN KEY (id_cuenta_destino, id_cliente)
        REFERENCES cuenta_cliente (id_cuenta, id_cliente),
    CONSTRAINT ck_operacion_cuentas CHECK (id_cuenta_origen <> id_cuenta_destino),
    CONSTRAINT ck_operacion_motivo CHECK ((estado_actual = 'Rechazada') = (motivo_rechazo IS NOT NULL)),
    CONSTRAINT ck_operacion_fechas CHECK (fecha_actualizacion >= fecha_operacion)
);
COMMENT ON TABLE operacion IS 'Operación de cambio; los montos, monedas y tasa se obtienen de su cotización.';

CREATE TABLE comprobante (
    id_comprobante    BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_operacion      BIGINT        NOT NULL REFERENCES operacion (id_operacion) ON DELETE CASCADE,
    nombre_archivo    VARCHAR(120)  NOT NULL,
    content_type      VARCHAR(20)   NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png',
                                                                     'image/webp', 'application/pdf')),
    tamano_bytes      INTEGER       NOT NULL CHECK (tamano_bytes BETWEEN 1 AND 4194304),  -- máx. 4 MB
    ruta_s3           VARCHAR(500)  NOT NULL UNIQUE CHECK (ruta_s3 ~ '^s3://'),
    fecha_subida      TIMESTAMPTZ   NOT NULL DEFAULT now()
);
COMMENT ON TABLE comprobante IS 'Metadatos del comprobante de transferencia; el archivo vive en Amazon S3.';

CREATE TABLE historial_estado (
    id_historial      BIGINT        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_operacion      BIGINT        NOT NULL REFERENCES operacion (id_operacion) ON DELETE CASCADE,
    estado_anterior   VARCHAR(25),  -- NULL en el primer registro
    estado_nuevo      VARCHAR(25)   NOT NULL,
    -- NULL cuando el cambio lo origina el sistema o el cliente.
    id_usuario        BIGINT        REFERENCES usuario_backoffice (id_usuario),
    comentario        VARCHAR(300),
    fecha_cambio      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    -- Máquina de estados del negocio (COALESCE: un NULL en IN haría pasar cualquier valor).
    CONSTRAINT ck_historial_transicion CHECK (
        (COALESCE(estado_anterior, '(inicio)'), estado_nuevo) IN (
            ('(inicio)',                 'Pendiente de comprobante'),
            ('Pendiente de comprobante', 'Pendiente de validación'),
            ('Pendiente de validación',  'En proceso'),
            ('Pendiente de validación',  'Rechazada'),
            ('En proceso',               'Procesada'),
            ('En proceso',               'Rechazada'))),
    -- Las decisiones de validación las toma siempre un usuario de back-office.
    CONSTRAINT ck_historial_responsable CHECK (
        estado_nuevo NOT IN ('En proceso', 'Procesada', 'Rechazada') OR id_usuario IS NOT NULL),
    -- La máquina de estados no tiene ciclos: cada estado se alcanza una sola vez.
    CONSTRAINT uq_historial_estado UNIQUE (id_operacion, estado_nuevo)
);
COMMENT ON TABLE historial_estado IS 'Auditoría de cada transición de estado de una operación.';
