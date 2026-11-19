-- =============================================================================
-- Consultas sobre el JSON de bronze.context (§4 F)
-- Operadores usados: ->  ->>  @>  ?  jsonb_object_keys  jsonb_each_text
--                    jsonb_path_query  -  (borrar claves)  jsonb_typeof
-- =============================================================================

-- J1. ¿Qué tipos de registros hay en las bitácoras? (->> extrae texto)
SELECT value ->> 'source'       AS fuente,
       value ->> 'context_type' AS tipo,
       count(*)                 AS registros
  FROM bronze.context
 GROUP BY 1, 2
 ORDER BY registros DESC
 LIMIT 20;

-- J2. Entrenamientos GPU por modelo: épocas, batch y tamaño del modelo
--     (@> usa el índice GIN jsonb_path_ops; ->> + cast para números)
SELECT value ->> 'model'                           AS modelo,
       count(*)                                    AS tareas,
       round(avg((value ->> 'epochs')::int), 1)    AS epocas_promedio,
       mode() WITHIN GROUP (ORDER BY (value ->> 'batch_size')::int) AS batch_mas_usado,
       max((value ->> 'model_params')::bigint)     AS parametros,
       round(avg("end" - start) / 60.0, 1)         AS duracion_media_min
  FROM bronze.context
 WHERE value @> '{"context_type": "gpu_cnn_training_workload"}'
 GROUP BY 1
 ORDER BY tareas DESC;

-- J3. Compilaciones CPU: librerías más compiladas y núcleos usados
SELECT split_part(value ->> 'library', '/', 2) AS libreria,      -- 'boost/units' → 'units'
       count(*)                                AS compilaciones,
       round(avg((value ->> 'cpu_cores_active')::int), 1) AS nucleos_promedio,
       sum((value ->> 'task_files')::int)      AS archivos
  FROM bronze.context
 WHERE value @> '{"context_type": "cpu_compilation_workload"}'
 GROUP BY 1
 ORDER BY compilaciones DESC
 LIMIT 15;

-- J4. Esfuerzo estimado por un LLM vs duración real de la tarea
SELECT value ->> 'context_type'                AS tipo,
       value ->> 'llm_estimated_task_effort'   AS esfuerzo_estimado,
       count(*)                                AS tareas,
       round(avg("end" - start) / 60.0, 1)     AS duracion_media_min
  FROM bronze.context
 WHERE value ? 'llm_estimated_task_effort'
 GROUP BY 1, 2
 ORDER BY 1, 4;

-- J5. JSON anidado: métricas de los minutos con la red caída (-> devuelve jsonb, ->> texto)
SELECT date_trunc('month', to_timestamp(start) AT TIME ZONE 'Asia/Shanghai')::date AS mes,
       count(*)                                                                     AS minutos_sin_red,
       round(avg((value -> 'metrics' ->> 'ac_load_w_mean')::numeric), 1)            AS carga_media_w,
       round(avg((value -> 'metrics' ->> 'pv_power_w_mean')::numeric), 1)           AS fv_media_w
  FROM bronze.context
 WHERE value @> '{"context_type": "grid_unavailable_or_islanded"}'
 GROUP BY 1
 ORDER BY 1;

-- J6. JSONPath: ¿el modelo más grande es el más costoso? Modelos con > 100 M de parámetros
--     o con esfuerzo estimado alto. (Todas las tareas GPU tienen 2 épocas.)
--     Hallazgo: los VGG (> 130 M parámetros) duran ~3,7 min y se estiman de esfuerzo bajo/medio;
--     swin_v2_s (50 M) dura 13,2 min: la duración depende de la arquitectura, no del tamaño.
SELECT value ->> 'model'                     AS modelo,
       (value ->> 'model_params')::bigint    AS parametros,
       value ->> 'llm_estimated_task_effort' AS esfuerzo_estimado,
       count(*)                              AS tareas,
       round(avg("end" - start) / 60.0, 1)   AS duracion_media_min
  FROM bronze.context
 WHERE value @? '$ ? (@.context_type == "gpu_cnn_training_workload"
                      && (@.model_params > 100000000 || @.llm_estimated_task_effort == "high"))'
 GROUP BY 1, 2, 3
 ORDER BY duracion_media_min DESC;

-- J7. Descubrir la estructura: qué claves trae cada tipo de registro y de qué tipo son
SELECT value ->> 'context_type' AS tipo, k.clave, jsonb_typeof(value -> k.clave) AS tipo_json, count(*) AS veces
  FROM bronze.context, jsonb_object_keys(value) AS k(clave)
 WHERE value ->> 'context_type' IN ('gpu_cnn_training_workload', 'cpu_compilation_workload')
 GROUP BY 1, 2, 3
 ORDER BY 1, 4 DESC;

-- J8. Calendario académico: festivos y vacaciones de las entradas manuales
--     (no traen context_type; alimentan dim_fecha.tipo_dia = 'Festivo' y periodo_academico)
SELECT value ->> 'textual_description'                          AS descripcion,
       (to_timestamp(start)   AT TIME ZONE 'Asia/Shanghai')::date AS desde,
       (to_timestamp("end")   AT TIME ZONE 'Asia/Shanghai')::date AS hasta
  FROM bronze.context
 WHERE value @> '{"source": "manual entry"}'
   AND NOT value ? 'context_type'
   AND value ->> 'textual_description' ~* 'holiday|festival|new year'
 ORDER BY start;

-- J9. Privacidad (Ley 1581): el operador - quita las claves sensibles antes de pasar a Silver
SELECT id,
       value - ARRAY['command', 'directory', 'example_commands_redacted',
                     'sanitized_message', 'sample_record_ids'] AS value_sin_datos_personales
  FROM bronze.context
 WHERE value ?| ARRAY['command', 'directory', 'example_commands_redacted']
 LIMIT 5;
