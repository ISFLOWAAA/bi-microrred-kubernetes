-- =============================================================================
-- 02 · Capa Silver: datos limpios, en hora local y agregados a 1 minuto,
-- más las tablas de auditoría del ETL (ejecuciones, calidad y conciliación).
-- =============================================================================

-- ---------------------------------------------------------------- Auditoría
CREATE TABLE IF NOT EXISTS silver.etl_ejecucion (
    ejecucion_id   bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inicio         timestamptz NOT NULL DEFAULT now(),
    fin            timestamptz,
    estado         text        NOT NULL DEFAULT 'en curso'
                   CHECK (estado IN ('en curso', 'exitosa', 'fallida')),
    fuente_archivo text        NOT NULL,
    fuente_sha256  text,
    version_etl    text,
    mensaje        text
);
COMMENT ON TABLE silver.etl_ejecucion IS 'Una fila por ejecución del ETL: evidencia de que el Job terminó y con qué resultado.';

CREATE TABLE IF NOT EXISTS silver.calidad_log (
    ejecucion_id    bigint  NOT NULL REFERENCES silver.etl_ejecucion ON DELETE CASCADE,
    orden           smallint NOT NULL,
    regla           text    NOT NULL,        -- p. ej. Q1, Q4
    descripcion     text    NOT NULL,
    tabla           text    NOT NULL,
    filas_antes     bigint  NOT NULL,
    filas_afectadas bigint  NOT NULL,
    filas_despues   bigint  NOT NULL,
    accion          text    NOT NULL,        -- descartar / anular / recortar / marcar
    PRIMARY KEY (ejecucion_id, orden)
);
COMMENT ON TABLE silver.calidad_log IS 'Conteos antes y después de cada regla de limpieza (§4 E).';

CREATE TABLE IF NOT EXISTS silver.conciliacion (
    ejecucion_id   bigint  NOT NULL REFERENCES silver.etl_ejecucion ON DELETE CASCADE,
    metrica        text    NOT NULL,
    inversor_id    smallint NOT NULL DEFAULT 0,   -- 0 = total
    valor_fuente   numeric NOT NULL,
    valor_cargado  numeric NOT NULL,
    diferencia     numeric GENERATED ALWAYS AS (valor_cargado - valor_fuente) STORED,
    diferencia_pct numeric GENERATED ALWAYS AS (
                       CASE WHEN valor_fuente = 0 THEN NULL
                            ELSE round((valor_cargado - valor_fuente) / valor_fuente * 100, 3) END) STORED,
    explicacion    text,
    PRIMARY KEY (ejecucion_id, metrica, inversor_id)
);
COMMENT ON TABLE silver.conciliacion IS 'Totales de la fuente vs totales cargados (§4 E: reconciliation).';

-- ---------------------------------------------------------------- Lecturas por minuto
CREATE TABLE IF NOT EXISTS silver.lectura_minuto (
    inversor_id        smallint     NOT NULL CHECK (inversor_id IN (1, 2)),
    ts_minuto          timestamptz  NOT NULL,
    fecha_local        date         NOT NULL,
    minuto_dia         smallint     NOT NULL CHECK (minuto_dia BETWEEN 0 AND 1439),
    n_lecturas         smallint     NOT NULL CHECK (n_lecturas > 0),
    n_lecturas_validas smallint     NOT NULL CHECK (n_lecturas_validas BETWEEN 0 AND n_lecturas),
    segundos_cubiertos numeric(5,1) NOT NULL CHECK (segundos_cubiertos BETWEEN 0 AND 60),
    e_fv_wh            numeric(10,3) CHECK (e_fv_wh >= 0),
    e_carga_wh         numeric(10,3) CHECK (e_carga_wh >= 0),
    e_red_wh           numeric(10,3) CHECK (e_red_wh >= 0),
    e_bat_carga_wh     numeric(10,3) CHECK (e_bat_carga_wh >= 0),
    e_bat_descarga_wh  numeric(10,3) CHECK (e_bat_descarga_wh >= 0),
    p_fv_w             numeric(8,1),
    p_carga_w          numeric(8,1),
    p_red_w            numeric(8,1),
    p_carga_max_w      integer,
    soc_pct            numeric(5,1) CHECK (soc_pct BETWEEN 0 AND 100),
    soc_min_pct        numeric(5,1) CHECK (soc_min_pct BETWEEN 0 AND 100),
    v_bateria_v        numeric(6,2),
    v_red_v            numeric(6,2),
    temp_max_c         numeric(5,1),
    modo_salida_cod    smallint,     -- moda de status.outstatus en el minuto
    estado_carga_cod   smallint,     -- moda de status.chgstatus en el minuto
    regimen_red        text NOT NULL CHECK (regimen_red IN ('Conectado', 'Isla', 'Sin dato')),
    origen             text NOT NULL DEFAULT 'historico' CHECK (origen IN ('historico', 'simulado')),
    PRIMARY KEY (inversor_id, ts_minuto)
);
COMMENT ON TABLE silver.lectura_minuto IS 'Grano: un inversor en un minuto (UTC). Lecturas limpias integradas a energía.';

-- ---------------------------------------------------------------- Contadores diarios del inversor
CREATE TABLE IF NOT EXISTS silver.estadistica_diaria (
    inversor_id                 smallint NOT NULL,
    fecha_local                 date     NOT NULL,
    e_fv_kwh_contador           numeric(8,3),
    e_consumo_kwh_contador      numeric(8,3),
    e_red_carga_kwh_contador    numeric(8,3),
    e_red_bateria_kwh_contador  numeric(8,3),
    e_bat_carga_kwh_contador    numeric(8,3),
    e_bat_descarga_kwh_contador numeric(8,3),
    PRIMARY KEY (inversor_id, fecha_local)
);

-- ---------------------------------------------------------------- Configuración diaria (base del SCD 2)
CREATE TABLE IF NOT EXISTS silver.config_diaria (
    inversor_id          smallint NOT NULL,
    fecha_local          date     NOT NULL,
    firmware_build       text,
    version_lib          text,
    prioridad_salida     smallint,
    prioridad_carga      smallint,
    potencia_max_red_w   integer,
    capacidad_bateria_ah integer,
    soc_alarma_pct       smallint,
    soc_corte_pct        smallint,
    PRIMARY KEY (inversor_id, fecha_local)
);

-- ---------------------------------------------------------------- Contexto parseado (sin datos personales)
CREATE TABLE IF NOT EXISTS silver.contexto (
    contexto_id    integer     PRIMARY KEY,          -- = bronze.context.id
    ts_registro    timestamptz,
    ts_inicio      timestamptz,
    ts_fin         timestamptz,
    fuente         text,
    dispositivo    text,
    inversor_id    smallint,
    tipo_contexto  text,
    atributos      jsonb NOT NULL DEFAULT '{}'::jsonb, -- solo campos técnicos permitidos
    CHECK (ts_fin IS NULL OR ts_inicio IS NULL OR ts_fin >= ts_inicio)
);
CREATE INDEX IF NOT EXISTS ix_silver_contexto_tipo ON silver.contexto (tipo_contexto, ts_inicio);

-- ---------------------------------------------------------------- Eventos detectados
CREATE TABLE IF NOT EXISTS silver.evento (
    inversor_id      smallint    NOT NULL,           -- 0 = sitio completo
    codigo           text        NOT NULL,
    ts_inicio        timestamptz NOT NULL,
    ts_fin           timestamptz NOT NULL,
    valor_referencia numeric(10,2),
    dispositivo      text,
    detalle          jsonb,
    origen_id        text,
    PRIMARY KEY (inversor_id, codigo, ts_inicio),
    CHECK (ts_fin >= ts_inicio)
);
