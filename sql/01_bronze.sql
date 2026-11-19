-- =============================================================================
-- 01 · Capa Bronze
-- El archivo .sqlite es la capa Bronze oficial y nunca se modifica.
-- Aquí solo se copia 1:1 la tabla context, con value como jsonb, para poder
-- consultarla con los operadores JSON nativos de PostgreSQL (§4 F).
-- =============================================================================

CREATE TABLE IF NOT EXISTS bronze.context (
    id          integer     PRIMARY KEY,           -- context.id
    recorded    bigint,                            -- s Unix UTC: cuándo se anotó
    start       bigint,                            -- s Unix UTC: inicio del intervalo
    "end"       bigint,                            -- s Unix UTC: fin del intervalo
    value       jsonb       NOT NULL,              -- JSON original sin tocar
    cargado_en  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE bronze.context IS
    'Copia 1:1 de opencem-v1.0.0.sqlite → context. value es el JSON original (incluye campos sensibles: no se expone a los tableros).';

-- Búsquedas por contenido del JSON: value @> '{"context_type": "..."}'
-- jsonb_path_ops es más pequeño y rápido que el GIN por defecto para el operador @>.
CREATE INDEX IF NOT EXISTS ix_bronze_context_value
    ON bronze.context USING gin (value jsonb_path_ops);

-- Cruce de intervalos [start, end] con la telemetría
CREATE INDEX IF NOT EXISTS ix_bronze_context_intervalo
    ON bronze.context (start, "end");
