-- =============================================================================
-- 05 · Capa Gold: vistas de indicadores (catálogo de docs/03)
-- Las vistas calculan los KPI y los costos al vuelo: cambiar la tarifa en
-- gold.dim_tarifa cambia los resultados sin recargar los hechos.
-- Power BI usa solo origen = 'historico'; Grafana ve también lo simulado.
-- =============================================================================

-- ---------------------------------------------------------------- KPI mensuales (P1, P2, P3 · K1–K11)
CREATE OR REPLACE VIEW gold.v_kpi_mensual AS
WITH ventana AS (                       -- días del periodo con datos, para K4
    SELECT min(fecha_key) AS desde, max(fecha_key) AS hasta
      FROM gold.fact_energia_minuto
     WHERE origen = 'historico'
),
dias AS (
    SELECT f.anio_mes, count(*) AS dias_periodo, min(f.fecha) AS primer_dia
      FROM gold.dim_fecha f, ventana v
     WHERE f.fecha_key BETWEEN v.desde AND v.hasta
     GROUP BY f.anio_mes
),
-- Energía oficial del mes: suma de la energía oficial diaria = contador del inversor
-- (sin los huecos de comunicación que sí afectan la integración, docs/02 §5) y, en
-- los días sin contador, la energía integrada de las lecturas.
energia AS (
    SELECT d.inversor_id, f.anio_mes,
           sum(d.e_fv_kwh_oficial)            AS e_fv_kwh,
           sum(d.e_carga_kwh_oficial)         AS e_carga_kwh,
           sum(d.e_red_kwh_oficial)           AS e_red_kwh,
           sum(d.e_bat_carga_kwh_oficial)     AS e_bat_carga_kwh,
           sum(d.e_bat_descarga_kwh_oficial)  AS e_bat_descarga_kwh,
           count(*) FILTER (WHERE d.fuente_energia = 'Contador del inversor') AS dias_con_contador,
           count(*)                                                          AS dias_con_datos
      FROM gold.fact_energia_diaria d
      JOIN gold.dim_fecha f USING (fecha_key)
     GROUP BY d.inversor_id, f.anio_mes
),
-- Calidad del registro y régimen de red: desde las lecturas por minuto
mes AS (
    SELECT m.inversor_id,
           f.anio_mes,
           sum(m.segundos_cubiertos)        AS segundos_cubiertos,
           sum(m.n_lecturas)                AS n_lecturas,
           sum(m.n_lecturas_validas)        AS n_lecturas_validas,
           count(*) FILTER (WHERE e.regimen_red = 'Isla') AS minutos_isla,
           count(*)                                       AS minutos_con_datos
      FROM gold.fact_energia_minuto m
      JOIN gold.dim_fecha f            USING (fecha_key)
      JOIN gold.dim_estado_operativo e USING (estado_key)
     WHERE m.origen = 'historico'
     GROUP BY m.inversor_id, f.anio_mes
)
SELECT mes.inversor_id,
       mes.anio_mes,
       round(en.e_fv_kwh, 2)                                                     AS k1_energia_solar_kwh,
       round(en.e_carga_kwh, 2)                                                  AS k2_energia_carga_kwh,
       round(en.e_red_kwh, 2)                                                    AS k3_energia_red_kwh,
       round(100 * mes.segundos_cubiertos / (d.dias_periodo * 86400.0), 2)       AS k4_disponibilidad_pct,
       round(100.0 * mes.n_lecturas_validas / nullif(mes.n_lecturas, 0), 2)      AS k5_datos_validos_pct,
       round(100 * (1 - en.e_red_kwh / nullif(en.e_carga_kwh, 0)), 2)            AS k6_autosuficiencia_pct,
       round(en.e_bat_descarga_kwh / nullif(i.capacidad_bateria_kwh, 0)
             / d.dias_periodo, 3)                                                AS k7_ciclos_bateria_dia,
       round(100.0 * mes.minutos_isla / nullif(mes.minutos_con_datos, 0), 2)     AS k8_tiempo_isla_pct,
       round(mes.minutos_isla / 60.0, 1)                                         AS k8_horas_isla,
       round(100 * (en.e_fv_kwh + en.e_red_kwh + en.e_bat_descarga_kwh
                    - en.e_carga_kwh - en.e_bat_carga_kwh)
             / nullif(en.e_fv_kwh + en.e_red_kwh + en.e_bat_descarga_kwh, 0), 2) AS k9_perdidas_pct,
       round(en.e_red_kwh * gold.tarifa_cop_kwh(d.primer_dia), 0)                AS k10_costo_red_cop,
       round((en.e_carga_kwh - en.e_red_kwh) * gold.tarifa_cop_kwh(d.primer_dia), 0) AS k11_ahorro_cop,
       round(100.0 * en.dias_con_contador / nullif(en.dias_con_datos, 0), 1)     AS dias_con_contador_pct
  FROM mes
  JOIN dias d USING (anio_mes)
  LEFT JOIN energia en USING (inversor_id, anio_mes)
  LEFT JOIN gold.dim_inversor i ON i.inversor_id = mes.inversor_id AND i.es_vigente;

COMMENT ON VIEW gold.v_kpi_mensual IS
    'Indicadores K1–K11 por inversor y mes (solo histórico). Energía: contadores del inversor; calidad e isla: lecturas.';

-- ---------------------------------------------------------------- Costo por franja horaria (K12)
-- La energía importada del mes es la del contador (K3); las lecturas por minuto solo
-- dicen qué parte cayó en punta y qué parte fuera de punta.
CREATE OR REPLACE VIEW gold.v_costo_franja_mensual AS
WITH franja AS (
    SELECT m.inversor_id, f.anio_mes, h.franja_tarifaria,
           sum(m.e_red_wh) AS e_red_wh, min(f.fecha) AS primer_dia
      FROM gold.fact_energia_minuto m
      JOIN gold.dim_fecha f USING (fecha_key)
      JOIN gold.dim_hora  h USING (hora_key)
     WHERE m.origen = 'historico'
     GROUP BY m.inversor_id, f.anio_mes, h.franja_tarifaria
),
reparto AS (
    SELECT *, e_red_wh / nullif(sum(e_red_wh) OVER (PARTITION BY inversor_id, anio_mes), 0) AS participacion
      FROM franja
)
SELECT r.inversor_id,
       r.anio_mes,
       r.franja_tarifaria,
       round(k.k3_energia_red_kwh * r.participacion, 2)                                     AS e_red_kwh,
       gold.tarifa_cop_kwh(r.primer_dia, 'Oficial', r.franja_tarifaria)                     AS tarifa_cop_kwh,
       round(k.k3_energia_red_kwh * r.participacion
             * gold.tarifa_cop_kwh(r.primer_dia, 'Oficial', r.franja_tarifaria), 0)         AS k12_costo_cop
  FROM reparto r
  JOIN gold.v_kpi_mensual k USING (inversor_id, anio_mes);

-- ---------------------------------------------------------------- Estado actual (P5, P6, P7 · Grafana)
CREATE OR REPLACE VIEW gold.v_estado_actual AS
SELECT DISTINCT ON (m.inversor_id)
       m.inversor_id,
       m.ts_minuto                                                AS ultima_lectura,
       round(extract(epoch FROM now() - m.ts_minuto) / 60, 1)     AS minutos_sin_datos,   -- O4
       m.soc_pct,                                                                          -- O1
       e.regimen_red,                                                                      -- O2
       m.v_red_v,
       m.temp_max_c,                                                                       -- O3
       m.p_fv_w, m.p_carga_w, m.p_red_w,
       e.modo_salida, e.estado_carga,
       m.origen
  FROM gold.fact_energia_minuto m
  JOIN gold.dim_estado_operativo e USING (estado_key)
 ORDER BY m.inversor_id, m.ts_minuto DESC;

COMMENT ON VIEW gold.v_estado_actual IS 'Última fila de cada inversor (histórico o simulado) para los paneles de estado de Grafana.';

-- ---------------------------------------------------------------- SolarBI por perfil de tarea (P8, P9, P11 · S1–S4)
CREATE OR REPLACE VIEW gold.v_solarbi_perfil AS
SELECT p.categoria,
       CASE WHEN p.categoria = 'Entrenamiento GPU' THEN p.modelo ELSE p.libreria END AS modelo_o_libreria,
       count(*)                                                        AS tareas,
       round(sum(t.duracion_min) / 60, 1)                              AS horas,
       round(sum(t.e_incremental_wh) / 1000, 3)                        AS s1_energia_incremental_kwh,
       round(avg(t.e_incremental_wh), 1)                               AS s1_wh_por_tarea,
       round(sum(t.e_incremental_wh) / nullif(sum(t.epocas), 0), 2)    AS s2_wh_por_epoca,
       round(100 * sum(t.e_fv_wh) / nullif(sum(t.e_carga_wh), 0), 1)   AS s3_fraccion_solar_pct,
       round(sum(t.costo_cop), 0)                                      AS s4_costo_cop,
       round(avg(t.cobertura_pct), 1)                                  AS cobertura_media_pct
  FROM gold.fact_tarea_computo t
  JOIN gold.dim_perfil_tarea p USING (perfil_tarea_key)
 GROUP BY 1, 2;

-- ---------------------------------------------------------------- SolarBI por hora del día (P10 · S5)
CREATE OR REPLACE VIEW gold.v_solarbi_hora AS
SELECT h.hora,
       a.categoria                                                            AS actividad,
       count(*)                                                               AS minutos,
       round(avg(m.p_carga_w), 1)                                             AS carga_media_w,
       round(avg(m.p_fv_w), 1)                                                AS fv_media_w,
       round(avg(m.p_red_w), 1)                                               AS red_media_w,
       round(100.0 * count(*) FILTER (WHERE m.p_fv_w > 0) / count(*), 1)       AS s5_minutos_con_sol_pct
  FROM gold.fact_energia_minuto m
  JOIN gold.dim_hora h              USING (hora_key)
  JOIN gold.dim_actividad_computo a USING (actividad_key)
 WHERE m.origen = 'historico'
   AND m.actividad_key > 0                 -- solo la ventana con bitácoras
 GROUP BY h.hora, a.categoria;

-- ---------------------------------------------------------------- Para Power BI: hora local ya calculada
-- timestamptz → hora local del sitio como timestamp sin zona: el conector de Power BI lo recibe sin ambigüedad
-- y el modelo no necesita convertir zonas horarias. Sin las columnas JSON ni de origen.
CREATE OR REPLACE VIEW gold.v_pbi_evento AS
SELECT evento_id, inversor_id, tipo_evento_key,
       ts_inicio AT TIME ZONE 'Asia/Shanghai' AS ts_inicio,
       ts_fin    AT TIME ZONE 'Asia/Shanghai' AS ts_fin,
       duracion_min, fecha_key, hora_key, inversor_sk, dispositivo_key, valor_referencia
  FROM gold.fact_evento_operativo;

CREATE OR REPLACE VIEW gold.v_pbi_tarea AS
SELECT tarea_id, fecha_key, hora_key, inversor_sk, dispositivo_key, perfil_tarea_key,
       ts_inicio AT TIME ZONE 'Asia/Shanghai' AS ts_inicio,
       ts_fin    AT TIME ZONE 'Asia/Shanghai' AS ts_fin,
       duracion_min, epocas, batch_size, parametros_modelo, nucleos_cpu, archivos,
       e_carga_wh, e_incremental_wh, e_fv_wh, e_red_wh, fraccion_solar, costo_cop, cobertura_pct
  FROM gold.fact_tarea_computo;
