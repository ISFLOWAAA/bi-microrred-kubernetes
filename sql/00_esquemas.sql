-- =============================================================================
-- 00 · Esquemas por capa (Medallion: Bronze → Silver → Gold)
-- Idempotente: se puede ejecutar varias veces.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;   -- copia 1:1 de la fuente (solo context en jsonb)
CREATE SCHEMA IF NOT EXISTS silver;   -- datos limpios, agregados a 1 minuto, auditoría del ETL
CREATE SCHEMA IF NOT EXISTS gold;     -- modelo en estrella para Power BI y Grafana

COMMENT ON SCHEMA bronze IS 'Capa Bronze: copia sin transformar de la fuente OpenCEM v1.0.0';
COMMENT ON SCHEMA silver IS 'Capa Silver: datos limpios en hora local, grano de 1 minuto, auditoría del ETL';
COMMENT ON SCHEMA gold   IS 'Capa Gold: modelo dimensional (estrella) para consumo analítico y operativo';

-- La zona horaria de la sesión no afecta los datos (se guardan en timestamptz),
-- pero las fechas y horas locales del sitio se calculan siempre en Asia/Shanghai.
