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
mes AS (
    SELECT m.inversor_id,
           f.anio_mes,
           sum(m.e_fv_wh)            / 1000 AS e_fv_kwh,
           sum(m.e_carga_wh)         / 1000 AS e_carga_kwh,
           sum(m.e_red_wh)           / 1000 AS e_red_kwh,
           sum(m.e_bat_carga_wh)     / 1000 AS e_bat_carga_kwh,
           sum(m.e_bat_descarga_wh)  / 1000 AS e_bat_descarga_kwh,
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
       round(mes.e_fv_kwh, 2)                                                    AS k1_energia_solar_kwh,
       round(mes.e_carga_kwh, 2)                                                 AS k2_energia_carga_kwh,
       round(mes.e_red_kwh, 2)                                                   AS k3_energia_red_kwh,
       round(100 * mes.segundos_cubiertos / (d.dias_periodo * 86400.0), 2)       AS k4_disponibilidad_pct,
       round(100.0 * mes.n_lecturas_validas / nullif(mes.n_lecturas, 0), 2)      AS k5_datos_validos_pct,
       round(100 * (1 - mes.e_red_kwh / nullif(mes.e_carga_kwh, 0)), 2)          AS k6_autosuficiencia_pct,
       round(mes.e_bat_descarga_kwh / nullif(i.capacidad_bateria_kwh, 0)
             / d.dias_periodo, 3)                                                AS k7_ciclos_bateria_dia,
       round(100.0 * mes.minutos_isla / nullif(mes.minutos_con_datos, 0), 2)     AS k8_tiempo_isla_pct,
       round(mes.minutos_isla / 60.0, 1)                                         AS k8_horas_isla,
       round(100 * (mes.e_fv_kwh + mes.e_red_kwh + mes.e_bat_descarga_kwh
                    - mes.e_carga_kwh - mes.e_bat_carga_kwh)
             / nullif(mes.e_fv_kwh + mes.e_red_kwh + mes.e_bat_descarga_kwh, 0), 2) AS k9_perdidas_pct,
       round(mes.e_red_kwh * gold.tarifa_cop_kwh(d.primer_dia), 0)               AS k10_costo_red_cop,
       round((mes.e_carga_kwh - mes.e_red_kwh) * gold.tarifa_cop_kwh(d.primer_dia), 0) AS k11_ahorro_cop
  FROM mes
  JOIN dias d USING (anio_mes)
  LEFT JOIN gold.dim_inversor i ON i.inversor_id = mes.inversor_id AND i.es_vigente;

COMMENT ON VIEW gold.v_kpi_mensual IS 'Indicadores K1–K11 por inversor y mes (solo histórico).';

-- ---------------------------------------------------------------- Costo por franja horaria (K12)
CREATE OR REPLACE VIEW gold.v_costo_franja_mensual AS
SELECT m.inversor_id,
       f.anio_mes,
       h.franja_tarifaria,
       round(sum(m.e_red_wh) / 1000, 2)                                                   AS e_red_kwh,
       gold.tarifa_cop_kwh(min(f.fecha), 'Oficial', h.franja_tarifaria)                   AS tarifa_cop_kwh,
       round(sum(m.e_red_wh) / 1000 * gold.tarifa_cop_kwh(min(f.fecha), 'Oficial', h.franja_tarifaria), 0) AS k12_costo_cop
  FROM gold.fact_energia_minuto m
  JOIN gold.dim_fecha f USING (fecha_key)
  JOIN gold.dim_hora  h USING (hora_key)
 WHERE m.origen = 'historico'
 GROUP BY m.inversor_id, f.anio_mes, h.franja_tarifaria;

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
