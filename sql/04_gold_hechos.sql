-- =============================================================================
-- 04 · Capa Gold: tablas de hechos
-- Las llaves foráneas nunca son nulas (se usa el miembro desconocido).
-- Las llaves únicas naturales permiten que el ETL sea idempotente (ON CONFLICT).
-- =============================================================================

-- ---------------------------------------------------------------- 1. Flujos de energía por minuto
-- Grano: un inversor en un minuto con al menos una lectura.
CREATE TABLE IF NOT EXISTS gold.fact_energia_minuto (
    ts_minuto          timestamptz  NOT NULL,
    inversor_id        smallint     NOT NULL CHECK (inversor_id IN (1, 2)),
    fecha_key          integer      NOT NULL DEFAULT 0  REFERENCES gold.dim_fecha,
    hora_key           smallint     NOT NULL DEFAULT -1 REFERENCES gold.dim_hora,
    inversor_sk        integer      NOT NULL DEFAULT 0  REFERENCES gold.dim_inversor,
    estado_key         smallint     NOT NULL DEFAULT 0  REFERENCES gold.dim_estado_operativo,
    actividad_key      smallint     NOT NULL DEFAULT 0  REFERENCES gold.dim_actividad_computo,
    n_lecturas         smallint     NOT NULL CHECK (n_lecturas > 0),
    n_lecturas_validas smallint     NOT NULL CHECK (n_lecturas_validas BETWEEN 0 AND n_lecturas),
    segundos_cubiertos numeric(5,1) NOT NULL CHECK (segundos_cubiertos BETWEEN 0 AND 60),
    -- Medidas aditivas (Wh)
    e_fv_wh            numeric(10,3) CHECK (e_fv_wh >= 0),
    e_carga_wh         numeric(10,3) CHECK (e_carga_wh >= 0),
    e_red_wh           numeric(10,3) CHECK (e_red_wh >= 0),
    e_bat_carga_wh     numeric(10,3) CHECK (e_bat_carga_wh >= 0),
    e_bat_descarga_wh  numeric(10,3) CHECK (e_bat_descarga_wh >= 0),
    -- Medidas no aditivas / semiaditivas (promedios del minuto para Grafana)
    p_fv_w             numeric(8,1),
    p_carga_w          numeric(8,1),
    p_red_w            numeric(8,1),
    p_carga_max_w      integer,
    soc_pct            numeric(5,1) CHECK (soc_pct BETWEEN 0 AND 100),
    soc_min_pct        numeric(5,1) CHECK (soc_min_pct BETWEEN 0 AND 100),
    v_bateria_v        numeric(6,2),
    v_red_v            numeric(6,2),
    temp_max_c         numeric(5,1),
    es_horario_solar   boolean,
    origen             text NOT NULL DEFAULT 'historico' CHECK (origen IN ('historico', 'simulado')),
    PRIMARY KEY (inversor_id, ts_minuto)
);
COMMENT ON TABLE gold.fact_energia_minuto IS
    'Grano: un inversor en un minuto. Energía en Wh (aditiva); SoC y temperatura son semiaditivas. origen separa histórico de simulado.';

-- La PK (inversor_id, ts_minuto) ya sirve a Grafana: "últimos N minutos del inversor X".
CREATE INDEX IF NOT EXISTS ix_fem_fecha     ON gold.fact_energia_minuto (fecha_key, inversor_id);
CREATE INDEX IF NOT EXISTS ix_fem_actividad ON gold.fact_energia_minuto (actividad_key);
CREATE INDEX IF NOT EXISTS ix_fem_ts        ON gold.fact_energia_minuto USING brin (ts_minuto);

-- ---------------------------------------------------------------- 2. Cierre diario y conciliación
-- Grano: un inversor en un día local con al menos una lectura.
CREATE TABLE IF NOT EXISTS gold.fact_energia_diaria (
    fecha_key                   integer  NOT NULL REFERENCES gold.dim_fecha,
    inversor_id                 smallint NOT NULL CHECK (inversor_id IN (1, 2)),
    inversor_sk                 integer  NOT NULL DEFAULT 0 REFERENCES gold.dim_inversor,
    -- Contadores diarios del propio inversor (máximo del día)
    e_fv_kwh_contador           numeric(8,3),
    e_consumo_kwh_contador      numeric(8,3),
    e_red_carga_kwh_contador    numeric(8,3),
    e_red_bateria_kwh_contador  numeric(8,3),
    e_bat_carga_kwh_contador    numeric(8,3),
    e_bat_descarga_kwh_contador numeric(8,3),
    -- Integrados desde fact_energia_minuto
    e_fv_kwh                    numeric(8,3),
    e_carga_kwh                 numeric(8,3),
    e_red_kwh                   numeric(8,3),
    minutos_con_datos           smallint CHECK (minutos_con_datos BETWEEN 0 AND 1440),
    disponibilidad_pct          numeric(5,2) CHECK (disponibilidad_pct BETWEEN 0 AND 100),   -- K4
    datos_validos_pct           numeric(5,2) CHECK (datos_validos_pct BETWEEN 0 AND 100),    -- K5
    minutos_en_isla             smallint CHECK (minutos_en_isla BETWEEN 0 AND 1440),          -- K8
    dif_fv_pct                  numeric(6,2),                                                 -- conciliación
    -- Energía oficial del día (la que usan los KPI): el contador del inversor si existe;
    -- si ese día no hay contador, la integrada (límite inferior por los huecos).
    e_fv_kwh_oficial            numeric(8,3),
    e_carga_kwh_oficial         numeric(8,3),
    e_red_kwh_oficial           numeric(8,3),
    e_bat_carga_kwh_oficial     numeric(8,3),
    e_bat_descarga_kwh_oficial  numeric(8,3),
    fuente_energia              text NOT NULL DEFAULT 'Contador del inversor'
                                CHECK (fuente_energia IN ('Contador del inversor', 'Integración de lecturas')),
    PRIMARY KEY (fecha_key, inversor_id)
);
COMMENT ON TABLE gold.fact_energia_diaria IS
    'Grano: un inversor en un día. Energía oficial (contador o integrada) y conciliación entre ambas.';

-- ---------------------------------------------------------------- 3. Eventos operativos
-- Grano: un evento (episodio con inicio y fin, o puntual si ts_fin = ts_inicio).
CREATE TABLE IF NOT EXISTS gold.fact_evento_operativo (
    evento_id        bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inversor_id      smallint    NOT NULL CHECK (inversor_id IN (0, 1, 2)),   -- 0 = sitio completo
    tipo_evento_key  smallint    NOT NULL DEFAULT 0  REFERENCES gold.dim_tipo_evento,
    ts_inicio        timestamptz NOT NULL,
    ts_fin           timestamptz NOT NULL,
    duracion_min     numeric(10,1) GENERATED ALWAYS AS (extract(epoch FROM ts_fin - ts_inicio) / 60) STORED,
    fecha_key        integer     NOT NULL DEFAULT 0  REFERENCES gold.dim_fecha,
    hora_key         smallint    NOT NULL DEFAULT -1 REFERENCES gold.dim_hora,
    inversor_sk      integer     NOT NULL DEFAULT 0  REFERENCES gold.dim_inversor,
    dispositivo_key  smallint    NOT NULL DEFAULT 0  REFERENCES gold.dim_dispositivo,
    valor_referencia numeric(10,2),
    detalle          jsonb,                         -- solo datos técnicos, sin información personal
    origen_id        text,                          -- dimensión degenerada: context.id o ranura de fault_history
    UNIQUE (inversor_id, tipo_evento_key, ts_inicio),
    CHECK (ts_fin >= ts_inicio)
);
CREATE INDEX IF NOT EXISTS ix_feo_tipo  ON gold.fact_evento_operativo (tipo_evento_key, ts_inicio);
CREATE INDEX IF NOT EXISTS ix_feo_fecha ON gold.fact_evento_operativo (fecha_key);

-- ---------------------------------------------------------------- 4. Tareas de cómputo (SolarBI)
-- Grano: una tarea registrada en las bitácoras JSON.
CREATE TABLE IF NOT EXISTS gold.fact_tarea_computo (
    tarea_id          integer     PRIMARY KEY,      -- dimensión degenerada: context.id
    fecha_key         integer     NOT NULL DEFAULT 0  REFERENCES gold.dim_fecha,
    hora_key          smallint    NOT NULL DEFAULT -1 REFERENCES gold.dim_hora,
    inversor_sk       integer     NOT NULL DEFAULT 0  REFERENCES gold.dim_inversor,
    dispositivo_key   smallint    NOT NULL DEFAULT 0  REFERENCES gold.dim_dispositivo,
    perfil_tarea_key  integer     NOT NULL DEFAULT 0  REFERENCES gold.dim_perfil_tarea,
    ts_inicio         timestamptz NOT NULL,
    ts_fin            timestamptz NOT NULL,
    duracion_min      numeric(8,2) GENERATED ALWAYS AS (extract(epoch FROM ts_fin - ts_inicio) / 60) STORED,
    epocas            integer,                      -- nulo en compilaciones CPU
    batch_size        integer,
    parametros_modelo bigint,
    nucleos_cpu       smallint,
    archivos          integer,
    e_carga_wh        numeric(10,3),
    e_incremental_wh  numeric(10,3),                -- S1 (puede ser negativa si la carga bajó de la línea base)
    e_fv_wh           numeric(10,3),
    e_red_wh          numeric(10,3),
    fraccion_solar    numeric(5,4) CHECK (fraccion_solar BETWEEN 0 AND 1),   -- S3: least(e_fv / e_carga, 1)
    costo_cop         numeric(12,2),                -- S4
    cobertura_pct     numeric(5,2) CHECK (cobertura_pct BETWEEN 0 AND 100),
    CHECK (ts_fin >= ts_inicio)
);
CREATE INDEX IF NOT EXISTS ix_ftc_perfil ON gold.fact_tarea_computo (perfil_tarea_key);
CREATE INDEX IF NOT EXISTS ix_ftc_fecha  ON gold.fact_tarea_computo (fecha_key);
