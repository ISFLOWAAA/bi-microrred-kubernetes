-- =============================================================================
-- Consultas de negocio: una por pregunta de docs/03_negocio_indicadores.md
-- Se ejecutan a mano (no al iniciar la base) cuando el ETL ya cargó datos.
-- =============================================================================

-- P1. ¿Cuánta energía aporta el sol frente a la red, por inversor y mes?
SELECT inversor_id, anio_mes,
       k1_energia_solar_kwh, k3_energia_red_kwh, k2_energia_carga_kwh,
       k6_autosuficiencia_pct
  FROM gold.v_kpi_mensual
 ORDER BY inversor_id, anio_mes;

-- P2. ¿Cuánto cuesta la energía comprada y cuánto se ahorra con el sol?
SELECT inversor_id,
       sum(k10_costo_red_cop) AS costo_red_cop,
       sum(k11_ahorro_cop)    AS ahorro_cop
  FROM gold.v_kpi_mensual
 GROUP BY ROLLUP (inversor_id)
 ORDER BY inversor_id NULLS LAST;

-- P3. ¿La batería se usa bien o está sobredimensionada? (meta: <= 1 ciclo/día)
SELECT inversor_id, anio_mes, k7_ciclos_bateria_dia,
       CASE WHEN k7_ciclos_bateria_dia > 1    THEN 'Desgaste alto'
            WHEN k7_ciclos_bateria_dia < 0.3  THEN 'Posible sobredimensionamiento'
            ELSE 'Uso adecuado' END AS diagnostico
  FROM gold.v_kpi_mensual
 ORDER BY inversor_id, anio_mes;

-- P4. ¿Qué pasaría con la tarifa industrial y comercial? (what-if de tarifa)
SELECT k.inversor_id,
       round(sum(k.k3_energia_red_kwh) * gold.tarifa_cop_kwh(CURRENT_DATE, 'Oficial'), 0)                AS costo_oficial_cop,
       round(sum(k.k3_energia_red_kwh) * gold.tarifa_cop_kwh(CURRENT_DATE, 'Industrial y comercial'), 0) AS costo_comercial_cop
  FROM gold.v_kpi_mensual k
 GROUP BY k.inversor_id;

-- P4 (bis). Costo según franja horaria: ¿cuánto se paga en punta? (K12)
SELECT inversor_id, franja_tarifaria, sum(e_red_kwh) AS e_red_kwh, sum(k12_costo_cop) AS costo_cop
  FROM gold.v_costo_franja_mensual
 GROUP BY inversor_id, franja_tarifaria
 ORDER BY inversor_id, franja_tarifaria;

-- P5, P6, P7. ¿Cómo está cada inversor ahora? ¿Hay red? ¿Llegan datos?
SELECT inversor_id, ultima_lectura, minutos_sin_datos, soc_pct, regimen_red, temp_max_c,
       CASE WHEN minutos_sin_datos > 2 THEN 'ALERTA: sin datos'          -- O4
            WHEN soc_pct < 20          THEN 'ALERTA: batería baja'       -- O1
            WHEN regimen_red = 'Isla'  THEN 'Aviso: en modo isla'        -- O2
            WHEN temp_max_c > 45       THEN 'ALERTA: temperatura alta'   -- O3
            ELSE 'Normal' END AS estado
  FROM gold.v_estado_actual;

-- P6 (histórico). Cortes de red: cuántos y cuánto duraron, por mes
SELECT f.anio_mes, e.inversor_id,
       count(*)                          AS cortes,
       round(sum(e.duracion_min) / 60, 1) AS horas_sin_red,
       max(e.duracion_min)               AS corte_mas_largo_min
  FROM gold.fact_evento_operativo e
  JOIN gold.dim_tipo_evento t USING (tipo_evento_key)
  JOIN gold.dim_fecha f       USING (fecha_key)
 WHERE t.codigo = 'RED_CAIDA'
 GROUP BY f.anio_mes, e.inversor_id
 ORDER BY f.anio_mes, e.inversor_id;

-- P8. ¿Cuánta energía consume cada tipo de tarea y modelo?
SELECT categoria, modelo_o_libreria, tareas, horas,
       s1_energia_incremental_kwh, s1_wh_por_tarea, s2_wh_por_epoca
  FROM gold.v_solarbi_perfil
 ORDER BY s1_energia_incremental_kwh DESC NULLS LAST;

-- P9. ¿Qué parte de esa energía es solar?
SELECT categoria, round(100 * sum(e_fv_wh) / nullif(sum(e_carga_wh), 0), 1) AS fraccion_solar_pct
  FROM gold.fact_tarea_computo
  JOIN gold.dim_perfil_tarea USING (perfil_tarea_key)
 GROUP BY categoria;

-- P10. ¿En qué horario conviene entrenar? Horas con más sol y su uso actual por la GPU
SELECT hora, minutos AS minutos_gpu, fv_media_w, red_media_w, s5_minutos_con_sol_pct
  FROM gold.v_solarbi_hora
 WHERE actividad = 'Cómputo intensivo'
 ORDER BY hora;

-- P11. ¿Cuánto cuesta la energía de cada tarea y de cada mes?
SELECT f.anio_mes, p.categoria,
       count(*)                    AS tareas,
       round(sum(t.costo_cop), 0)  AS costo_cop,
       round(avg(t.costo_cop), 2)  AS costo_medio_por_tarea_cop
  FROM gold.fact_tarea_computo t
  JOIN gold.dim_perfil_tarea p USING (perfil_tarea_key)
  JOIN gold.dim_fecha f        USING (fecha_key)
 GROUP BY f.anio_mes, p.categoria
 ORDER BY f.anio_mes, p.categoria;

-- SCD 2. ¿Mejoró la autosuficiencia después de cada cambio de configuración?
SELECT i.inversor_id, i.vigente_desde, i.vigente_hasta, i.prioridad_carga, i.prioridad_salida,
       round(100 * (1 - sum(m.e_red_wh) / nullif(sum(m.e_carga_wh), 0)), 2) AS autosuficiencia_pct
  FROM gold.fact_energia_minuto m
  JOIN gold.dim_inversor i USING (inversor_sk)
 WHERE m.origen = 'historico'
 GROUP BY i.inversor_sk, i.inversor_id, i.vigente_desde, i.vigente_hasta, i.prioridad_carga, i.prioridad_salida
 ORDER BY i.inversor_id, i.vigente_desde;

-- Conciliación: días donde la energía integrada difiere más de 5 % del contador del inversor
SELECT f.fecha, d.inversor_id, d.e_fv_kwh, d.e_fv_kwh_contador, d.dif_fv_pct, d.disponibilidad_pct
  FROM gold.fact_energia_diaria d
  JOIN gold.dim_fecha f USING (fecha_key)
 WHERE abs(d.dif_fv_pct) > 5
 ORDER BY abs(d.dif_fv_pct) DESC;
