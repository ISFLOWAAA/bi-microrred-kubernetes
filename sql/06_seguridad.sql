-- =============================================================================
-- 06 · Seguridad: roles por función (principio de mínimo privilegio)
-- Aquí se crean solo ROLES SIN LOGIN (grupos). Los usuarios con contraseña se crean
-- al desplegar, leyendo las credenciales desde un Secret de Kubernetes; nunca
-- quedan en el repositorio.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_etl') THEN
        CREATE ROLE rol_etl NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_lectura_bi') THEN
        CREATE ROLE rol_lectura_bi NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_simulador') THEN
        CREATE ROLE rol_simulador NOLOGIN;
    END IF;
END $$;

-- Nadie crea objetos en public
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ETL: escribe en las tres capas
GRANT USAGE, CREATE ON SCHEMA bronze, silver, gold TO rol_etl;
GRANT ALL ON ALL TABLES    IN SCHEMA bronze, silver, gold TO rol_etl;
GRANT ALL ON ALL SEQUENCES IN SCHEMA bronze, silver, gold TO rol_etl;

-- Power BI y Grafana: solo lectura de Gold.
-- Sin acceso a bronze (el JSON original puede tener datos personales: Ley 1581 de 2012).
GRANT USAGE ON SCHEMA gold TO rol_lectura_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO rol_lectura_bi;
REVOKE ALL ON SCHEMA bronze FROM rol_lectura_bi;

-- Simulador: inserta lecturas nuevas y lee las dimensiones para resolver llaves
GRANT USAGE ON SCHEMA gold TO rol_simulador;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO rol_simulador;
GRANT INSERT, UPDATE, DELETE ON gold.fact_energia_minuto TO rol_simulador;

-- Que las tablas y vistas futuras hereden los mismos permisos
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO rol_lectura_bi, rol_simulador;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze, silver, gold GRANT ALL ON TABLES TO rol_etl;
