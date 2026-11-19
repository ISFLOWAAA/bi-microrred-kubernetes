-- =============================================================================
-- Carga Silver → Gold. La ejecuta etl.py paso a paso (cada "-- @paso" es un paso),
-- dentro de la misma transacción que la carga de Silver.
-- Idempotente: upsert por llave natural (ON CONFLICT ... DO UPDATE) y borrado de lo
-- que ya no está en Silver. Las llaves sustitutas existentes no cambian.
-- Requiere la tabla temporal tmp_versiones (versiones SCD 2 calculadas en Python).
-- =============================================================================

-- @paso dim_fecha: festivos y periodo académico desde las entradas manuales de context
WITH cal AS (
    SELECT atributos ->> 'textual_description'                                    AS texto,
           (ts_inicio AT TIME ZONE 'Asia/Shanghai')::date                          AS desde,
           (greatest(ts_fin - interval '1 second', ts_inicio) AT TIME ZONE 'Asia/Shanghai')::date AS hasta
      FROM silver.contexto
     WHERE tipo_contexto = 'manual_entry' AND inversor_id IS NULL
)
UPDATE gold.dim_fecha f
   SET tipo_dia = CASE
           WHEN EXISTS (SELECT 1 FROM cal WHERE f.fecha BETWEEN desde AND hasta
                                            AND texto ~* 'holiday|festival|new year') THEN 'Festivo'
           WHEN f.es_fin_de_semana THEN 'Fin de semana'
           ELSE 'Laboral' END,
       periodo_academico = CASE
           WHEN f.fecha > (SELECT max(hasta) FROM cal) THEN 'Sin dato'
           WHEN EXISTS (SELECT 1 FROM cal WHERE f.fecha BETWEEN desde AND hasta AND texto ~* 'exam')          THEN 'Exámenes'
           WHEN EXISTS (SELECT 1 FROM cal WHERE f.fecha BETWEEN desde AND hasta AND texto ~* 'teaching term') THEN 'Clases'
           WHEN EXISTS (SELECT 1 FROM cal WHERE f.fecha BETWEEN desde AND hasta AND texto ~* 'summer term')   THEN 'Verano'
           ELSE 'Vacaciones' END
 WHERE f.fecha_key > 0;

-- @paso dim_dispositivo: hardware desde las entradas manuales
UPDATE gold.dim_dispositivo d
   SET hardware = x.hw
  FROM (SELECT DISTINCT ON (dispositivo) dispositivo,
               (regexp_match(atributos ->> 'textual_description', 'CPU:\s*([^;]+);\s*GPU:\s*([^.]+)'))[1] || ' + ' ||
               (regexp_match(atributos ->> 'textual_description', 'CPU:\s*([^;]+);\s*GPU:\s*([^.]+)'))[2] AS hw
          FROM silver.contexto
         WHERE tipo_contexto = 'manual_entry'
           AND atributos ->> 'textual_description' ILIKE '%hardware configuration%'
         ORDER BY dispositivo, ts_inicio DESC) x
 WHERE d.codigo = x.dispositivo;

-- @paso dim_inversor: versiones SCD tipo 2
INSERT INTO gold.dim_inversor (inversor_id, nombre, cargas, firmware_build, version_lib, prioridad_salida,
                               prioridad_carga, potencia_max_red_w, capacidad_bateria_ah, soc_alarma_pct,
                               soc_corte_pct, vigente_desde, vigente_hasta)
SELECT inversor_id, nombre, cargas, firmware_build, version_lib, prioridad_salida, prioridad_carga,
       potencia_max_red_w, capacidad_bateria_ah, soc_alarma_pct, soc_corte_pct, vigente_desde, vigente_hasta
  FROM tmp_versiones
ON CONFLICT (inversor_id, vigente_desde) DO UPDATE SET
    nombre = EXCLUDED.nombre, cargas = EXCLUDED.cargas, firmware_build = EXCLUDED.firmware_build,
    version_lib = EXCLUDED.version_lib, prioridad_salida = EXCLUDED.prioridad_salida,
    prioridad_carga = EXCLUDED.prioridad_carga, potencia_max_red_w = EXCLUDED.potencia_max_red_w,
    capacidad_bateria_ah = EXCLUDED.capacidad_bateria_ah, soc_alarma_pct = EXCLUDED.soc_alarma_pct,
    soc_corte_pct = EXCLUDED.soc_corte_pct, vigente_hasta = EXCLUDED.vigente_hasta;

-- Llave sustituta de cada versión nueva (evita mezclar con versiones viejas que se borran al final)
CREATE TEMP TABLE tmp_sk AS
SELECT d.inversor_sk, t.inversor_id, t.vigente_desde, t.vigente_hasta
  FROM tmp_versiones t
  JOIN gold.dim_inversor d USING (inversor_id, vigente_desde);

-- @paso dim_perfil_tarea
-- Tabla temporal (no vista) con estadísticas: así el planificador estima bien los cruces
CREATE TEMP TABLE tmp_tareas AS
SELECT contexto_id, ts_inicio, ts_fin, dispositivo, inversor_id,
       CASE tipo_contexto WHEN 'gpu_cnn_training_workload' THEN 'Entrenamiento GPU' ELSE 'Compilación CPU' END AS categoria,
       coalesce(atributos ->> 'model', 'N/A')                              AS modelo,
       coalesce(atributos ->> 'dataset', 'N/A')                            AS dataset,
       coalesce(atributos ->> 'optim', 'N/A')                              AS optimizador,
       coalesce(regexp_replace(atributos ->> 'library', '^.*/', ''), 'N/A') AS libreria,
       CASE atributos ->> 'llm_estimated_task_effort'
            WHEN 'low' THEN 'Bajo' WHEN 'medium' THEN 'Medio' WHEN 'high' THEN 'Alto' ELSE 'Sin dato' END AS esfuerzo,
       (atributos ->> 'epochs')::int                                       AS epocas,
       (atributos ->> 'batch_size')::int                                   AS batch_size,
       (atributos ->> 'model_params')::bigint                              AS parametros,
       CASE WHEN atributos ->> 'cpu_cores_active' ~ '^\d+$'
            THEN (atributos ->> 'cpu_cores_active')::smallint END          AS nucleos,
       (atributos ->> 'task_files')::int                                   AS archivos
  FROM silver.contexto
 WHERE tipo_contexto IN ('gpu_cnn_training_workload', 'cpu_compilation_workload');

ANALYZE tmp_tareas;

INSERT INTO gold.dim_perfil_tarea (categoria, modelo, dataset, optimizador, libreria, esfuerzo_estimado)
SELECT DISTINCT categoria, modelo, dataset, optimizador, libreria, esfuerzo
  FROM tmp_tareas
 ORDER BY 1, 2, 3, 4, 5, 6
ON CONFLICT (categoria, modelo, dataset, optimizador, libreria, esfuerzo_estimado) DO NOTHING;

-- @paso dim_tipo_evento: códigos de falla encontrados en fault_history
INSERT INTO gold.dim_tipo_evento (codigo, nombre, categoria, severidad, origen)
SELECT DISTINCT codigo, 'Falla del inversor, código ' || substr(codigo, 7), 'Inversor', 'Advertencia', 'fault_history'
  FROM silver.evento
 WHERE codigo LIKE 'FALLA\_%'
 ORDER BY codigo
ON CONFLICT (codigo) DO NOTHING;

-- @paso fact_energia_minuto
INSERT INTO gold.fact_energia_minuto (
       ts_minuto, inversor_id, fecha_key, hora_key, inversor_sk, estado_key, actividad_key,
       n_lecturas, n_lecturas_validas, segundos_cubiertos, e_fv_wh, e_carga_wh, e_red_wh,
       e_bat_carga_wh, e_bat_descarga_wh, p_fv_w, p_carga_w, p_red_w, p_carga_max_w,
       soc_pct, soc_min_pct, v_bateria_v, v_red_v, temp_max_c, es_horario_solar, origen)
SELECT l.ts_minuto, l.inversor_id, coalesce(f.fecha_key, 0), l.minuto_dia, coalesce(s.inversor_sk, 0),
       gold.estado_key(l.modo_salida_cod, l.estado_carga_cod, l.regimen_red), l.actividad_key,
       l.n_lecturas, l.n_lecturas_validas, l.segundos_cubiertos, l.e_fv_wh, l.e_carga_wh, l.e_red_wh,
       l.e_bat_carga_wh, l.e_bat_descarga_wh, l.p_fv_w, l.p_carga_w, l.p_red_w, l.p_carga_max_w,
       l.soc_pct, l.soc_min_pct, l.v_bateria_v, l.v_red_v, l.temp_max_c, l.es_horario_solar, 'historico'
  FROM silver.lectura_minuto l
  LEFT JOIN gold.dim_fecha f ON f.fecha = l.fecha_local
  LEFT JOIN tmp_sk s ON s.inversor_id = l.inversor_id AND l.fecha_local BETWEEN s.vigente_desde AND s.vigente_hasta
ON CONFLICT (inversor_id, ts_minuto) DO UPDATE SET
    fecha_key = EXCLUDED.fecha_key, hora_key = EXCLUDED.hora_key, inversor_sk = EXCLUDED.inversor_sk,
    estado_key = EXCLUDED.estado_key, actividad_key = EXCLUDED.actividad_key,
    n_lecturas = EXCLUDED.n_lecturas, n_lecturas_validas = EXCLUDED.n_lecturas_validas,
    segundos_cubiertos = EXCLUDED.segundos_cubiertos, e_fv_wh = EXCLUDED.e_fv_wh,
    e_carga_wh = EXCLUDED.e_carga_wh, e_red_wh = EXCLUDED.e_red_wh, e_bat_carga_wh = EXCLUDED.e_bat_carga_wh,
    e_bat_descarga_wh = EXCLUDED.e_bat_descarga_wh, p_fv_w = EXCLUDED.p_fv_w, p_carga_w = EXCLUDED.p_carga_w,
    p_red_w = EXCLUDED.p_red_w, p_carga_max_w = EXCLUDED.p_carga_max_w, soc_pct = EXCLUDED.soc_pct,
    soc_min_pct = EXCLUDED.soc_min_pct, v_bateria_v = EXCLUDED.v_bateria_v, v_red_v = EXCLUDED.v_red_v,
    temp_max_c = EXCLUDED.temp_max_c, es_horario_solar = EXCLUDED.es_horario_solar, origen = EXCLUDED.origen
-- Solo reescribe la fila si algo cambió: una segunda ejecución no toca nada (rápida e idempotente)
WHERE (gold.fact_energia_minuto.fecha_key, gold.fact_energia_minuto.hora_key, gold.fact_energia_minuto.inversor_sk,
       gold.fact_energia_minuto.estado_key, gold.fact_energia_minuto.actividad_key, gold.fact_energia_minuto.n_lecturas,
       gold.fact_energia_minuto.n_lecturas_validas, gold.fact_energia_minuto.segundos_cubiertos,
       gold.fact_energia_minuto.e_fv_wh, gold.fact_energia_minuto.e_carga_wh, gold.fact_energia_minuto.e_red_wh,
       gold.fact_energia_minuto.e_bat_carga_wh, gold.fact_energia_minuto.e_bat_descarga_wh,
       gold.fact_energia_minuto.p_fv_w, gold.fact_energia_minuto.p_carga_w, gold.fact_energia_minuto.p_red_w,
       gold.fact_energia_minuto.p_carga_max_w, gold.fact_energia_minuto.soc_pct, gold.fact_energia_minuto.soc_min_pct,
       gold.fact_energia_minuto.v_bateria_v, gold.fact_energia_minuto.v_red_v, gold.fact_energia_minuto.temp_max_c,
       gold.fact_energia_minuto.es_horario_solar, gold.fact_energia_minuto.origen)
      IS DISTINCT FROM
      (EXCLUDED.fecha_key, EXCLUDED.hora_key, EXCLUDED.inversor_sk, EXCLUDED.estado_key, EXCLUDED.actividad_key,
       EXCLUDED.n_lecturas, EXCLUDED.n_lecturas_validas, EXCLUDED.segundos_cubiertos, EXCLUDED.e_fv_wh,
       EXCLUDED.e_carga_wh, EXCLUDED.e_red_wh, EXCLUDED.e_bat_carga_wh, EXCLUDED.e_bat_descarga_wh,
       EXCLUDED.p_fv_w, EXCLUDED.p_carga_w, EXCLUDED.p_red_w, EXCLUDED.p_carga_max_w, EXCLUDED.soc_pct,
       EXCLUDED.soc_min_pct, EXCLUDED.v_bateria_v, EXCLUDED.v_red_v, EXCLUDED.temp_max_c,
       EXCLUDED.es_horario_solar, EXCLUDED.origen);

DELETE FROM gold.fact_energia_minuto g
 WHERE g.origen = 'historico'
   AND NOT EXISTS (SELECT 1 FROM silver.lectura_minuto l
                    WHERE l.inversor_id = g.inversor_id AND l.ts_minuto = g.ts_minuto);

ANALYZE gold.fact_energia_minuto;   -- lo usan los pasos siguientes

-- @paso fact_energia_diaria
WITH d AS (
    SELECT inversor_id, fecha_local,
           sum(e_fv_wh) / 1000 AS e_fv_kwh, sum(e_carga_wh) / 1000 AS e_carga_kwh, sum(e_red_wh) / 1000 AS e_red_kwh,
           sum(e_bat_carga_wh) / 1000 AS e_bat_carga_kwh, sum(e_bat_descarga_wh) / 1000 AS e_bat_descarga_kwh,
           count(*) AS minutos, sum(segundos_cubiertos) AS segundos,
           sum(n_lecturas_validas) AS validas, sum(n_lecturas) AS recibidas,
           count(*) FILTER (WHERE regimen_red = 'Isla') AS isla
      FROM silver.lectura_minuto
     GROUP BY inversor_id, fecha_local
)
INSERT INTO gold.fact_energia_diaria (
       fecha_key, inversor_id, inversor_sk, e_fv_kwh_contador, e_consumo_kwh_contador,
       e_red_carga_kwh_contador, e_red_bateria_kwh_contador, e_bat_carga_kwh_contador,
       e_bat_descarga_kwh_contador, e_fv_kwh, e_carga_kwh, e_red_kwh, minutos_con_datos,
       disponibilidad_pct, datos_validos_pct, minutos_en_isla, dif_fv_pct,
       e_fv_kwh_oficial, e_carga_kwh_oficial, e_red_kwh_oficial, e_bat_carga_kwh_oficial,
       e_bat_descarga_kwh_oficial, fuente_energia)
SELECT f.fecha_key, d.inversor_id, coalesce(s.inversor_sk, 0),
       e.e_fv_kwh_contador, e.e_consumo_kwh_contador, e.e_red_carga_kwh_contador,
       e.e_red_bateria_kwh_contador, e.e_bat_carga_kwh_contador, e.e_bat_descarga_kwh_contador,
       round(d.e_fv_kwh, 3), round(d.e_carga_kwh, 3), round(d.e_red_kwh, 3), d.minutos,
       round(least(d.segundos / 864.0, 100), 2),
       round(100.0 * d.validas / d.recibidas, 2),
       d.isla,
       CASE WHEN e.e_fv_kwh_contador >= 0.5
            THEN round((d.e_fv_kwh - e.e_fv_kwh_contador) / e.e_fv_kwh_contador * 100, 2) END,
       -- Energía oficial: contador si el día lo tiene; si no, la integrada (regla D1)
       CASE WHEN c.hay THEN e.e_fv_kwh_contador ELSE round(d.e_fv_kwh, 3) END,
       CASE WHEN c.hay THEN e.e_consumo_kwh_contador ELSE round(d.e_carga_kwh, 3) END,
       CASE WHEN c.hay THEN e.e_red_carga_kwh_contador + e.e_red_bateria_kwh_contador ELSE round(d.e_red_kwh, 3) END,
       CASE WHEN c.hay THEN e.e_bat_carga_kwh_contador ELSE round(d.e_bat_carga_kwh, 3) END,
       CASE WHEN c.hay THEN e.e_bat_descarga_kwh_contador ELSE round(d.e_bat_descarga_kwh, 3) END,
       CASE WHEN c.hay THEN 'Contador del inversor' ELSE 'Integración de lecturas' END
  FROM d
  JOIN gold.dim_fecha f ON f.fecha = d.fecha_local
  LEFT JOIN silver.estadistica_diaria e USING (inversor_id, fecha_local)
  CROSS JOIN LATERAL (SELECT e.e_consumo_kwh_contador IS NOT NULL AND e.e_fv_kwh_contador IS NOT NULL
                         AND e.e_red_carga_kwh_contador IS NOT NULL AND e.e_red_bateria_kwh_contador IS NOT NULL
                         AND e.e_bat_carga_kwh_contador IS NOT NULL AND e.e_bat_descarga_kwh_contador IS NOT NULL
                         AS hay) c
  LEFT JOIN tmp_sk s ON s.inversor_id = d.inversor_id AND d.fecha_local BETWEEN s.vigente_desde AND s.vigente_hasta
ON CONFLICT (fecha_key, inversor_id) DO UPDATE SET
    inversor_sk = EXCLUDED.inversor_sk, e_fv_kwh_contador = EXCLUDED.e_fv_kwh_contador,
    e_consumo_kwh_contador = EXCLUDED.e_consumo_kwh_contador,
    e_red_carga_kwh_contador = EXCLUDED.e_red_carga_kwh_contador,
    e_red_bateria_kwh_contador = EXCLUDED.e_red_bateria_kwh_contador,
    e_bat_carga_kwh_contador = EXCLUDED.e_bat_carga_kwh_contador,
    e_bat_descarga_kwh_contador = EXCLUDED.e_bat_descarga_kwh_contador,
    e_fv_kwh = EXCLUDED.e_fv_kwh, e_carga_kwh = EXCLUDED.e_carga_kwh, e_red_kwh = EXCLUDED.e_red_kwh,
    minutos_con_datos = EXCLUDED.minutos_con_datos, disponibilidad_pct = EXCLUDED.disponibilidad_pct,
    datos_validos_pct = EXCLUDED.datos_validos_pct, minutos_en_isla = EXCLUDED.minutos_en_isla,
    dif_fv_pct = EXCLUDED.dif_fv_pct, e_fv_kwh_oficial = EXCLUDED.e_fv_kwh_oficial,
    e_carga_kwh_oficial = EXCLUDED.e_carga_kwh_oficial, e_red_kwh_oficial = EXCLUDED.e_red_kwh_oficial,
    e_bat_carga_kwh_oficial = EXCLUDED.e_bat_carga_kwh_oficial,
    e_bat_descarga_kwh_oficial = EXCLUDED.e_bat_descarga_kwh_oficial, fuente_energia = EXCLUDED.fuente_energia;

DELETE FROM gold.fact_energia_diaria g
 WHERE NOT EXISTS (SELECT 1 FROM silver.lectura_minuto l JOIN gold.dim_fecha f ON f.fecha = l.fecha_local
                    WHERE l.inversor_id = g.inversor_id AND f.fecha_key = g.fecha_key);

-- @paso fact_evento_operativo
INSERT INTO gold.fact_evento_operativo (
       inversor_id, tipo_evento_key, ts_inicio, ts_fin, fecha_key, hora_key, inversor_sk,
       dispositivo_key, valor_referencia, detalle, origen_id)
SELECT e.inversor_id, t.tipo_evento_key, e.ts_inicio, e.ts_fin, coalesce(f.fecha_key, 0),
       (extract(hour FROM e.ts_inicio AT TIME ZONE 'Asia/Shanghai') * 60
        + extract(minute FROM e.ts_inicio AT TIME ZONE 'Asia/Shanghai'))::smallint,
       coalesce(s.inversor_sk, 0), coalesce(d.dispositivo_key, 0), e.valor_referencia, e.detalle, e.origen_id
  FROM silver.evento e
  JOIN gold.dim_tipo_evento t ON t.codigo = e.codigo
  LEFT JOIN gold.dim_fecha f ON f.fecha = (e.ts_inicio AT TIME ZONE 'Asia/Shanghai')::date
  LEFT JOIN tmp_sk s ON s.inversor_id = e.inversor_id AND f.fecha BETWEEN s.vigente_desde AND s.vigente_hasta
  LEFT JOIN gold.dim_dispositivo d ON d.codigo = e.dispositivo
ON CONFLICT (inversor_id, tipo_evento_key, ts_inicio) DO UPDATE SET
    ts_fin = EXCLUDED.ts_fin, fecha_key = EXCLUDED.fecha_key, hora_key = EXCLUDED.hora_key,
    inversor_sk = EXCLUDED.inversor_sk, dispositivo_key = EXCLUDED.dispositivo_key,
    valor_referencia = EXCLUDED.valor_referencia, detalle = EXCLUDED.detalle, origen_id = EXCLUDED.origen_id;

DELETE FROM gold.fact_evento_operativo g
 WHERE NOT EXISTS (SELECT 1 FROM silver.evento e JOIN gold.dim_tipo_evento t ON t.codigo = e.codigo
                    WHERE e.inversor_id = g.inversor_id AND t.tipo_evento_key = g.tipo_evento_key
                      AND e.ts_inicio = g.ts_inicio);

-- @paso fact_tarea_computo: energía de cada tarea repartida entre las tareas simultáneas
CREATE TEMP TABLE tmp_tarea_minuto AS
SELECT t.contexto_id, t.inversor_id, gs.m AS ts_minuto
  FROM tmp_tareas t,
       generate_series(date_trunc('minute', t.ts_inicio), date_trunc('minute', t.ts_fin), interval '1 minute') AS gs(m);

CREATE TEMP TABLE tmp_simultaneas AS
SELECT inversor_id, ts_minuto, count(*) AS n FROM tmp_tarea_minuto GROUP BY 1, 2;

ANALYZE tmp_tarea_minuto;
ANALYZE tmp_simultaneas;

WITH simultaneas AS (
    SELECT * FROM tmp_simultaneas
),
linea_base AS (   -- mediana de la carga en minutos sin tarea, por franja del día (S1)
    SELECT h.franja_dia, (percentile_cont(0.5) WITHIN GROUP (ORDER BY m.p_carga_w))::numeric AS base_w
      FROM gold.fact_energia_minuto m
      JOIN gold.dim_hora h USING (hora_key)
     WHERE m.actividad_key = 1 AND m.origen = 'historico'
     GROUP BY h.franja_dia
),
asignacion AS MATERIALIZED (   -- se calcula una sola vez (sin esto el plan la repetía por cada tarea)
    SELECT tm.contexto_id,
           count(*)                                                                  AS minutos_tarea,
           count(m.ts_minuto)                                                        AS minutos_con_dato,
           sum(m.e_carga_wh / sm.n)                                                  AS e_carga,
           sum((m.e_carga_wh - b.base_w * m.segundos_cubiertos / 3600.0) / sm.n)     AS e_incremental,
           sum(m.e_fv_wh / sm.n)                                                     AS e_fv,
           sum(m.e_red_wh / sm.n)                                                    AS e_red
      FROM tmp_tarea_minuto tm
      JOIN simultaneas sm USING (inversor_id, ts_minuto)
      LEFT JOIN gold.fact_energia_minuto m
             ON m.inversor_id = tm.inversor_id AND m.ts_minuto = tm.ts_minuto AND m.origen = 'historico'
      LEFT JOIN gold.dim_hora h ON h.hora_key = m.hora_key
      LEFT JOIN linea_base b ON b.franja_dia = h.franja_dia
     GROUP BY tm.contexto_id
),
calc AS (
    SELECT t.*, a.minutos_tarea, a.minutos_con_dato, a.e_carga, a.e_incremental, a.e_fv, a.e_red,
           least(greatest(a.e_fv / nullif(a.e_carga, 0), 0), 1)  AS fraccion,
           (t.ts_inicio AT TIME ZONE 'Asia/Shanghai')           AS local_inicio
      FROM tmp_tareas t JOIN asignacion a USING (contexto_id)
)
INSERT INTO gold.fact_tarea_computo (
       tarea_id, fecha_key, hora_key, inversor_sk, dispositivo_key, perfil_tarea_key, ts_inicio, ts_fin,
       epocas, batch_size, parametros_modelo, nucleos_cpu, archivos, e_carga_wh, e_incremental_wh,
       e_fv_wh, e_red_wh, fraccion_solar, costo_cop, cobertura_pct)
SELECT c.contexto_id, coalesce(f.fecha_key, 0),
       (extract(hour FROM c.local_inicio) * 60 + extract(minute FROM c.local_inicio))::smallint,
       coalesce(s.inversor_sk, 0), coalesce(d.dispositivo_key, 0), p.perfil_tarea_key,
       c.ts_inicio, c.ts_fin, c.epocas, c.batch_size, c.parametros, c.nucleos, c.archivos,
       round(c.e_carga, 3), round(c.e_incremental, 3), round(c.e_fv, 3), round(c.e_red, 3),
       round(c.fraccion, 4),
       round(greatest(c.e_incremental, 0) / 1000 * (1 - coalesce(c.fraccion, 0))
             * gold.tarifa_cop_kwh(c.local_inicio::date), 2),
       round(100.0 * c.minutos_con_dato / c.minutos_tarea, 2)
  FROM calc c
  JOIN gold.dim_perfil_tarea p
    ON (p.categoria, p.modelo, p.dataset, p.optimizador, p.libreria, p.esfuerzo_estimado)
     = (c.categoria, c.modelo, c.dataset, c.optimizador, c.libreria, c.esfuerzo)
  LEFT JOIN gold.dim_fecha f ON f.fecha = c.local_inicio::date
  LEFT JOIN tmp_sk s ON s.inversor_id = c.inversor_id AND f.fecha BETWEEN s.vigente_desde AND s.vigente_hasta
  LEFT JOIN gold.dim_dispositivo d ON d.codigo = c.dispositivo
ON CONFLICT (tarea_id) DO UPDATE SET
    fecha_key = EXCLUDED.fecha_key, hora_key = EXCLUDED.hora_key, inversor_sk = EXCLUDED.inversor_sk,
    dispositivo_key = EXCLUDED.dispositivo_key, perfil_tarea_key = EXCLUDED.perfil_tarea_key,
    ts_inicio = EXCLUDED.ts_inicio, ts_fin = EXCLUDED.ts_fin, epocas = EXCLUDED.epocas,
    batch_size = EXCLUDED.batch_size, parametros_modelo = EXCLUDED.parametros_modelo,
    nucleos_cpu = EXCLUDED.nucleos_cpu, archivos = EXCLUDED.archivos, e_carga_wh = EXCLUDED.e_carga_wh,
    e_incremental_wh = EXCLUDED.e_incremental_wh, e_fv_wh = EXCLUDED.e_fv_wh, e_red_wh = EXCLUDED.e_red_wh,
    fraccion_solar = EXCLUDED.fraccion_solar, costo_cop = EXCLUDED.costo_cop,
    cobertura_pct = EXCLUDED.cobertura_pct;

DELETE FROM gold.fact_tarea_computo g
 WHERE NOT EXISTS (SELECT 1 FROM tmp_tareas t WHERE t.contexto_id = g.tarea_id);

-- @paso limpiar versiones viejas del inversor que ya nadie usa
DELETE FROM gold.dim_inversor d
 WHERE d.inversor_id IN (1, 2)
   AND NOT EXISTS (SELECT 1 FROM tmp_versiones t WHERE t.inversor_id = d.inversor_id AND t.vigente_desde = d.vigente_desde)
   AND NOT EXISTS (SELECT 1 FROM gold.fact_energia_minuto   m WHERE m.inversor_sk = d.inversor_sk)
   AND NOT EXISTS (SELECT 1 FROM gold.fact_energia_diaria   m WHERE m.inversor_sk = d.inversor_sk)
   AND NOT EXISTS (SELECT 1 FROM gold.fact_evento_operativo m WHERE m.inversor_sk = d.inversor_sk)
   AND NOT EXISTS (SELECT 1 FROM gold.fact_tarea_computo    m WHERE m.inversor_sk = d.inversor_sk);

-- @paso estadísticas del planificador
ANALYZE gold.fact_energia_diaria;
ANALYZE gold.fact_evento_operativo;
ANALYZE gold.fact_tarea_computo;
