# Diccionario de datos (§4 D)

Convenciones:
- **PK** = llave primaria; **FK** = llave foránea; **UK** = llave única natural (garantiza la idempotencia).
- **Linaje:** `tabla.columna` de la fuente SQLite (Bronze). "Generado" = lo crea el ETL.
- Hora local = Asia/Shanghai (UTC+8). `Δt` = segundos hasta la siguiente lectura válida, tope de 60 s.
- Energía en Wh = Σ P[W] · Δt[s] / 3 600.

## 1. Unidades de las variables físicas y evidencia

| Variable fuente | Unidad | Evidencia 1: diccionario de los autores | Evidencia 2: valores observados |
|---|---|---|---|
| `read_ts` | s Unix, UTC | "fractional Unix timestamp in UTC" | Rango 2025-07-12 → 2026-07-13, consistente con el README del dataset |
| `battvolt` | V | `unit = V` | Mediana 53,5 V, rango 50–58 V → banco de 48 V nominales |
| `battcurr` | A (+ descarga, − carga) | "positive denotes discharge and negative denotes charge" | Con `chgstatus` = 1 (cargando) la media es −0,8 A |
| `battsoc` | % | `unit = %` | Rango 6–100 |
| `pv1power` | W | `unit = W` | Máx. 3 933 W; 0 de noche |
| `pv1volt` / `pv1curr` | V / A | `unit = V` / `A` | `pv1volt` × `pv1curr` / `pv1power` = 1,001 (mediana, 650 000 lecturas con FV > 200 W) |
| `outw_a` | W | `unit = W` | Mediana 280 W; integrada coincide al 99 % con `usedenergytoday` (kWh) |
| `linepowerw_a` | W (positivo = importación) | `unit = W` | Mínimo −146 W en solo 9 lecturas: no hay exportación |
| `linevolta` / `linefreq` | V / Hz | `unit = V` / `Hz` | 235 V y 50,0 Hz = red china; 0 cuando la red cae |
| `temper1` | °C | `unit = degrees C` | Mediana 30,7 °C, p99,9 44,8 °C |
| `*energytoday`, `*tday` | kWh | `unit = kWh` | `pvgeneratenergytoday` máx. 12,8 con FV pico de ~3,9 kW → kWh, no Wh |
| `battpackrateah` | Ah | Nombre del registro (*rate Ah*) | 200 en el inversor 1 (banco típico de 48 V × 200 Ah ≈ 9,6 kWh) |
| `context.start` / `end` / `recorded` | s Unix, UTC | Columnas INTEGER de tiempo | Coinciden con las fechas de `local_date` dentro del JSON |

Fuente del diccionario de los autores: `datos/zenodo/opencem-v1.0.0/documentation/column_dictionary.csv`.

---

## 2. Dimensiones (esquema `gold`)

### `dim_fecha`: un día local (calendario de 2025-07-01 a 2027-12-31: cubre el histórico y deja margen para el simulador)

| Columna | Tipo | Llave | Regla de transformación | Linaje |
|---|---|---|---|---|
| `fecha_key` | `integer` | PK | `YYYYMMDD` de la fecha | Generado |
| `fecha` | `date` | UK | Serie diaria `generate_series` | Generado |
| `anio`, `trimestre`, `mes`, `dia_mes` | `smallint` | | `extract()` de la fecha | Generado |
| `nombre_mes`, `nombre_dia` | `text` | | Nombre en español | Generado |
| `anio_mes` | `text` | | `'YYYY-MM'` (orden y etiquetas en Power BI) | Generado |
| `semana_iso`, `dia_semana` | `smallint` | | ISO 8601; lunes = 1 | Generado |
| `es_fin_de_semana` | `boolean` | | `dia_semana` ≥ 6 | Generado |
| `tipo_dia` | `text` | | `Festivo` si hay entrada manual "Public Holiday"; si no, `Fin de semana` o `Laboral` | `context.value ->> 'day_type'` (`calendar_day`) + entradas manuales |
| `periodo_academico` | `text` | | Clases / Exámenes / Vacaciones / Verano, según el intervalo manual que cubre la fecha | `context` (`source = 'manual entry'`, `textual_description`) |

### `dim_hora`: un minuto del día

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `hora_key` | `smallint` | PK | `hora × 60 + minuto` (0–1439) | Generado |
| `hora`, `minuto` | `smallint` | | | Generado |
| `hora_texto` | `text` | | `'HH:MM'` | Generado |
| `franja_dia` | `text` | | Madrugada 0–5, Mañana 6–11, Tarde 12–17, Noche 18–23 | Generado |
| `franja_tarifaria` | `text` | | `Punta` si 9 ≤ hora < 12 o 18 ≤ hora < 21; si no, `Fuera de punta` | Publicación de tarifas EPM, abril de 2026 |

### `dim_inversor`: versión de un inversor (SCD tipo 2)

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `inversor_sk` | `integer` identity | PK | Llave sustituta; 0 = desconocido | Generado |
| `inversor_id` | `smallint` | UK (con `vigente_desde`) | 1 o 2 | `*.inverter` |
| `nombre` | `text` | | `'Inversor ' || id` (SCD tipo 1) | Generado |
| `cargas` | `text` | | Inv. 1: estaciones de trabajo con GPU; inv. 2: climatización | `context` (dispositivos por inversor) + enunciado |
| `firmware_build` | `text` | | Arreglo de códigos ASCII → texto, p. ej. `Jul  1 2025 22:28:12` | `specs.cpubuidtime` |
| `version_lib` | `text` | | Primer código ASCII → letra (`[68,0]` → `D`) | `specs.libver` |
| `prioridad_salida` | `smallint` | | Moda diaria estable ≥ 3 días | `settings.outpriority` |
| `prioridad_carga` | `smallint` | | Igual | `settings.chgpriority` |
| `potencia_max_red_w` | `integer` | | Igual | `settings.maxlinepower` |
| `capacidad_bateria_ah` | `integer` | | Igual; si es 0 → 200 (supuesto Q11) | `settings.battpackrateah` |
| `capacidad_bateria_kwh` | `numeric(6,2)` | | `capacidad_bateria_ah × 48 / 1000` | Derivado |
| `soc_alarma_pct`, `soc_corte_pct` | `smallint` | | Moda | `settings.batsoclowalarm`, `settings.batstopsoc` |
| `vigente_desde` | `date` | | Primer día de la versión | Derivado |
| `vigente_hasta` | `date` | | Día anterior a la siguiente versión; `9999-12-31` si es la vigente | Derivado |
| `es_vigente` | `boolean` | | `vigente_hasta = '9999-12-31'` | Derivado |

### `dim_estado_operativo`: combinación de estados (*junk dimension*)

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `estado_key` | `smallint` | PK | Combinación enumerada; 0 = sin dato | Generado |
| `modo_salida_cod` | `smallint` | UK (compuesta) | Moda del minuto | `status.outstatus` |
| `modo_salida` | `text` | | 0 → Apagado / espera · 1 → Modo red · 2 → Modo inversor (batería/FV) · nulo → Sin dato. *Semántica deducida*: con 0, el 59 % del tiempo no hay red; con 2, la FV media es de 286 W | Deducido |
| `estado_carga_cod` | `smallint` | UK | Moda del minuto | `status.chgstatus` |
| `estado_carga` | `text` | | 0 → No carga · 1 → Cargando (corriente media −0,8 A) · otro → Otro | Deducido |
| `regimen_red` | `text` | UK | `Conectado` si `linevolta` > 0; `Isla` si = 0; `Sin dato` si es nulo | `analog_measurements.linevolta` |

### `dim_actividad_computo`: combinación de tareas activas (construida)

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `actividad_key` | `smallint` | PK | 0 = sin bitácora; 1–8 = combinaciones (§5.1 del modelo) | Generado |
| `gpu_activa`, `cpu_ws1_activa`, `cpu_ws2_activa` | `boolean` | UK | ¿El minuto cae dentro de algún intervalo `[start, end]` de ese tipo? | `context.start`, `context.end`, `value ->> 'context_type'`, `value ->> 'device'` |
| `n_tareas_activas` | `smallint` | | Suma de los booleanos | Derivado |
| `descripcion` | `text` | | p. ej. "GPU + CPU estación 1" | Derivado |
| `categoria` | `text` | | Sin bitácora / Ocioso / Cómputo ligero / Cómputo intensivo | Derivado |

### `dim_tipo_evento`

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `tipo_evento_key` | `smallint` | PK | | Generado |
| `codigo` | `text` | UK | `RED_CAIDA`, `SOC_BAJO`, `TEMP_ALTA`, `FALLA_<n>`, `ALARMA_SISTEMA`, `HUECO_DATOS`, tipos de `context` | Catálogo propio; `n` = primer elemento del arreglo de `fault_history.faulthistoryrecordNN` |
| `nombre` | `text` | | Descripción en español; las fallas: "Falla del inversor, código n" (sin catálogo público del fabricante) | Catálogo propio |
| `categoria` | `text` | | Red / Batería / Inversor / Estación de trabajo / Sitio / Calidad de datos | Catálogo propio |
| `severidad` | `text` | | Info / Advertencia / Crítica | Catálogo propio |
| `origen` | `text` | | Telemetría derivada / `fault_history` / `context` | |
| `es_calidad_dato` | `boolean` | | Sí solo para `HUECO_DATOS` | |

### `dim_perfil_tarea`

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `perfil_tarea_key` | `integer` identity | PK | | Generado |
| `categoria` | `text` | UK (compuesta) | `Compilación CPU` / `Entrenamiento GPU` | `value ->> 'context_type'` |
| `modelo` | `text` | UK | Nulo → `'N/A'` | `value ->> 'model'` |
| `dataset` | `text` | UK | | `value ->> 'dataset'` |
| `optimizador` | `text` | UK | | `value ->> 'optim'` |
| `libreria` | `text` | UK | `boost/dll` → `dll` (solo el nombre) | `value ->> 'library'` |
| `esfuerzo_estimado` | `text` | UK | low/medium/high → Bajo/Medio/Alto; `n/a` → Sin dato | `value ->> 'llm_estimated_task_effort'` |

### `dim_dispositivo`

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `dispositivo_key` | `smallint` | PK | 0 = no aplica | Generado |
| `codigo` | `text` | UK | `workstation1`, `workstation2`, `inverter`, `installation` | `value ->> 'device'` |
| `nombre` | `text` | | "Estación de trabajo 1", … | Generado |
| `tipo` | `text` | | Estación de trabajo / Inversor / Instalación | Generado |
| `inversor_id` | `smallint` | | Inversor que lo alimenta (moda de `value ->> 'inverter'`) | `context` |
| `hardware` | `text` | | p. ej. "Intel Xeon Gold 6526Y + NVIDIA RTX 2000" | Entradas manuales de `context` |

### `dim_tarifa` (parámetros)

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `tarifa_key` | `smallint` | PK | | Generado |
| `tipo_tarifa` | `text` | UK | Oficial / Industrial y comercial | EPM |
| `franja` | `text` | UK | Monomia / Punta / Fuera de punta | EPM |
| `valor_cop_kwh` | `numeric(10,2)` | | 864,06; 1 036,88; 870,79; 852,67 | EPM, abril de 2026 |
| `vigente_desde`, `vigente_hasta` | `date` | UK (`vigente_desde`) | | |
| `es_base` | `boolean` | | Sí para Oficial monomia | Decisión del equipo |
| `fuente` | `text` | | URL de la publicación | |

---

## 3. Hechos (esquema `gold`)

### `fact_energia_minuto`: un inversor en un minuto local

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `ts_minuto` | `timestamptz` | PK (con `inversor_id`) | `date_trunc('minute', to_timestamp(read_ts))` | `analog_measurements.read_ts` |
| `inversor_id` | `smallint` | PK | | `analog_measurements.inverter` |
| `fecha_key` | `integer` | FK → `dim_fecha` | Fecha local de `ts_minuto` | Derivado |
| `hora_key` | `smallint` | FK → `dim_hora` | Minuto local del día | Derivado |
| `inversor_sk` | `integer` | FK → `dim_inversor` | Versión vigente en la fecha | Derivado (SCD 2) |
| `estado_key` | `smallint` | FK → `dim_estado_operativo` | Combinación de modas del minuto | `status`, `linevolta` |
| `actividad_key` | `smallint` | FK → `dim_actividad_computo` | Tareas activas en el minuto | `context` |
| `n_lecturas` | `smallint` | | Lecturas recibidas en el minuto | Conteo |
| `n_lecturas_validas` | `smallint` | | Lecturas que pasan las reglas Q1–Q7 | Conteo |
| `segundos_cubiertos` | `numeric(5,1)` | | Σ Δt del minuto (máx. 60) → base de la disponibilidad | Derivado |
| `e_fv_wh` | `numeric(10,3)` | | Σ `pv1power` · Δt / 3600 | `pv1power` |
| `e_carga_wh` | `numeric(10,3)` | | Σ `outw_a` · Δt / 3600 | `outw_a` |
| `e_red_wh` | `numeric(10,3)` | | Σ max(`linepowerw_a`, 0) · Δt / 3600 | `linepowerw_a` |
| `e_bat_carga_wh` | `numeric(10,3)` | | Σ max(−`battvolt`·`battcurr`, 0) · Δt / 3600 | `battvolt`, `battcurr` |
| `e_bat_descarga_wh` | `numeric(10,3)` | | Σ max(`battvolt`·`battcurr`, 0) · Δt / 3600 | `battvolt`, `battcurr` |
| `p_fv_w`, `p_carga_w`, `p_red_w` | `numeric(8,1)` | | Promedio del minuto (para Grafana) | Ídem |
| `p_carga_max_w` | `integer` | | Máximo del minuto | `outw_a` |
| `soc_pct`, `soc_min_pct` | `numeric(5,1)` | | Promedio y mínimo (**semiaditivas**: no se suman en el tiempo) | `battsoc` |
| `v_bateria_v`, `v_red_v` | `numeric(6,2)` | | Promedio | `battvolt`, `linevolta` |
| `temp_max_c` | `numeric(5,1)` | | Máximo de `temper1` válido (Q5) | `temper1` |
| `es_horario_solar` | `boolean` | | Dentro de un intervalo `solar_daylight` de `context` | `context` |
| `origen` | `text` | | `historico` (ETL) o `simulado` (simulador) | Generado |

### `fact_energia_diaria`: un inversor en un día local

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `fecha_key` | `integer` | PK, FK | | Derivado |
| `inversor_id` | `smallint` | PK | | |
| `inversor_sk` | `integer` | FK | Versión vigente | SCD 2 |
| `e_fv_kwh_contador` | `numeric(8,3)` | | Máximo del día del contador diario (se reinicia a medianoche) | `statistics.pvgeneratenergytoday` |
| `e_consumo_kwh_contador` | `numeric(8,3)` | | Ídem | `statistics.usedenergytoday` |
| `e_red_carga_kwh_contador` | `numeric(8,3)` | | Ídem (red → carga) | `statistics.loadconsumlinetday` |
| `e_red_bateria_kwh_contador` | `numeric(8,3)` | | Ídem (red → batería) | `statistics.linechgenergytday` |
| `e_bat_carga_kwh_contador`, `e_bat_descarga_kwh_contador` | `numeric(8,3)` | | Ídem | `statistics.batchgenergytoday`, `batdischgenergytoday` |
| `e_fv_kwh`, `e_carga_kwh`, `e_red_kwh` | `numeric(8,3)` | | Σ del día de `fact_energia_minuto` / 1000 | Derivado |
| `minutos_con_datos` | `smallint` | | Minutos con al menos una lectura | Derivado |
| `disponibilidad_pct` | `numeric(5,2)` | | Σ `segundos_cubiertos` / 86 400 × 100 (**K4**) | Derivado |
| `datos_validos_pct` | `numeric(5,2)` | | Σ válidas / Σ recibidas × 100 (**K5**) | Derivado |
| `minutos_en_isla` | `smallint` | | Minutos con régimen `Isla` (**K8**) | Derivado |
| `dif_fv_pct` | `numeric(6,2)` | | (`e_fv_kwh` − `e_fv_kwh_contador`) / `e_fv_kwh_contador` × 100: **conciliación** | Derivado |

### `fact_evento_operativo`: un evento

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `evento_id` | `bigint` identity | PK | | Generado |
| `inversor_id` | `smallint` | UK (con tipo y `ts_inicio`) | | Fuente según el tipo |
| `tipo_evento_key` | `smallint` | UK, FK | | `dim_tipo_evento` |
| `ts_inicio` | `timestamptz` | UK | Primer minuto del episodio / hora de la falla | Derivado / `faulthistoryrecordNN_time` / `context.start` |
| `ts_fin` | `timestamptz` | | Último minuto del episodio; igual a `ts_inicio` si es puntual | Derivado / `context.end` |
| `duracion_min` | `numeric(10,1)` | | (`ts_fin` − `ts_inicio`) en minutos | Derivado |
| `fecha_key`, `hora_key` | | FK | Del `ts_inicio` local | Derivado |
| `inversor_sk` | `integer` | FK | Versión vigente | SCD 2 |
| `dispositivo_key` | `smallint` | FK | 0 si no aplica | `context` |
| `valor_referencia` | `numeric(10,2)` | | SoC mínimo, temperatura máxima, código de falla, etc. | Derivado |
| `detalle` | `jsonb` | | Datos técnicos sin información personal (p. ej. payload de la falla) | `fault_history`, `context.value` filtrado |
| `origen_id` | `text` | | `context.id` o `ranura NN` de `fault_history` (dimensión degenerada) | |

### `fact_tarea_computo`: una tarea registrada (SolarBI)

| Columna | Tipo | Llave | Regla | Linaje |
|---|---|---|---|---|
| `tarea_id` | `integer` | PK | Dimensión degenerada | `context.id` |
| `fecha_key`, `hora_key` | | FK | Del inicio local | `context.start` |
| `inversor_sk` | `integer` | FK | | `value ->> 'inverter'` |
| `dispositivo_key` | `smallint` | FK | | `value ->> 'device'` |
| `perfil_tarea_key` | `integer` | FK | | JSON (ver `dim_perfil_tarea`) |
| `ts_inicio`, `ts_fin` | `timestamptz` | | | `context.start`, `context.end` |
| `duracion_min` | `numeric(8,2)` | | | Derivado |
| `epocas`, `batch_size` | `integer` | | Nulo para CPU | `value ->> 'epochs'`, `'batch_size'` |
| `parametros_modelo` | `bigint` | | | `value ->> 'model_params'` |
| `nucleos_cpu` | `smallint` | | Texto → entero | `value ->> 'cpu_cores_active'` |
| `archivos` | `integer` | | | `value ->> 'task_files'` |
| `e_carga_wh` | `numeric(10,3)` | | Σ `e_carga_wh` de los minutos de la tarea / tareas activas en el minuto | `fact_energia_minuto` |
| `e_incremental_wh` | `numeric(10,3)` | | Σ (`p_carga_w` − línea base de la franja) · minutos / tareas activas (**S1**) | Derivado |
| `e_fv_wh`, `e_red_wh` | `numeric(10,3)` | | Parte proporcional de FV y red en esos minutos | Derivado |
| `fraccion_solar` | `numeric(5,4)` | | `e_fv_wh` / `e_carga_wh` (**S3**) | Derivado |
| `costo_cop` | `numeric(12,2)` | | `e_incremental_wh` / 1000 × (1 − `fraccion_solar`) × tarifa base (**S4**) | Derivado + `dim_tarifa` |
| `cobertura_pct` | `numeric(5,2)` | | % de los minutos de la tarea con telemetría | Derivado |

---

## 4. Capa Silver (resumen)

| Tabla | Grano | Contenido |
|---|---|---|
| `silver.lectura_minuto` | inversor × minuto | Lecturas limpias agregadas, con indicadores de calidad (base de `fact_energia_minuto`) |
| `silver.config_diaria` | inversor × día | Moda diaria de `settings` y `specs` (base del SCD 2) |
| `silver.contexto` | registro de `context` | JSON parseado en columnas, sin campos personales |
| `silver.evento` | evento | Episodios detectados y fallas deduplicadas |
| `silver.calidad_log` | ejecución × regla | Conteos antes y después de cada regla de limpieza (evidencia de §4 E) |

## 5. Columnas de la fuente que no se cargan (y por qué)

| Columnas | Motivo |
|---|---|
| `normalloadw_a`, `sir` | Siempre en 0 (Q8) |
| `*reserve`, `otherreserve`, `grid_reserve` | Registros reservados sin semántica pública |
| `generatedpower*`, `busvolt*`, `fanduty`, `temper2-4` | No los requieren los indicadores; quedan en Bronze por si se necesitan |
| 160 columnas de `settings` | Solo se usan las que alimentan el SCD 2 |
| `context.value`: `command`, `directory`, `example_commands_redacted`, `sanitized_message`, `sample_record_ids` | **Privacidad** (Ley 1581 de 2012): pueden revelar rutas, usuarios o hábitos personales |
