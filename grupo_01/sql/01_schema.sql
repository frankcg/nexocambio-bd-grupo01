-- =============================================================================
-- NexoCambio · 01_schema.sql
-- Crea el esquema del proyecto. Se ejecuta conectado a la base "nexocambio".
--
-- Una sola vez, desde la base postgres:
--   CREATE DATABASE nexocambio ENCODING 'UTF8' TEMPLATE template0;
-- =============================================================================

DROP SCHEMA IF EXISTS nexocambio CASCADE;

CREATE SCHEMA nexocambio;

COMMENT ON SCHEMA nexocambio IS
    'Casa de cambio digital de divisas y criptoactivos: clientes, cotizaciones, operaciones y back-office.';

-- El negocio opera en Lima; las fechas se guardan como TIMESTAMPTZ (UTC interno).
ALTER DATABASE nexocambio SET timezone TO 'America/Lima';
ALTER DATABASE nexocambio SET search_path TO nexocambio, public;
