# sql/

Scripts de PostgreSQL 16 para la base `microrred` (Fase 4, §4 F).

## Scripts de creación (se ejecutan en orden)

PostgreSQL los ejecuta automáticamente la primera vez que arranca si esta carpeta se monta en
`/docker-entrypoint-initdb.d` (los archivos sueltos `.sql`, en orden alfabético; la subcarpeta
`consultas/` y este README se ignoran). Todos son **idempotentes**: se pueden volver a ejecutar sin
errores ni filas duplicadas (`CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE`, `ON CONFLICT DO NOTHING`).

| Archivo | Qué crea |
|---|---|
| `00_esquemas.sql` | Esquemas `bronze`, `silver` y `gold` |
| `01_bronze.sql` | `bronze.context` (copia 1:1 con `value` como `jsonb`) + índice GIN `jsonb_path_ops` |
| `02_silver.sql` | Datos limpios a 1 minuto, configuración diaria, contexto sin datos personales, eventos y auditoría del ETL (`etl_ejecucion`, `calidad_log`, `conciliacion`) |
| `03_gold_dimensiones.sql` | Las 8 dimensiones + `dim_tarifa`, con sus semillas y miembros "desconocido" |
| `04_gold_hechos.sql` | Los 4 hechos: `fact_energia_minuto`, `fact_energia_diaria`, `fact_evento_operativo`, `fact_tarea_computo` |
| `05_gold_vistas.sql` | Vistas de indicadores para Power BI y Grafana |
| `06_seguridad.sql` | Roles sin login: `rol_etl`, `rol_lectura_bi`, `rol_simulador` (mínimo privilegio) |
| `07_usuarios_consumo.sh` | Usuarios con login de solo lectura: `grafana_lector` y `powerbi_lector` (miembros de `rol_lectura_bi`); las contraseñas llegan por variables de entorno, nunca en el repo |

## Funciones de apoyo (las usan el ETL y el simulador)

| Función | Para qué |
|---|---|
| `gold.inversor_sk_vigente(inversor_id, fecha)` | Versión del inversor (SCD 2) vigente en una fecha; 0 si no hay |
| `gold.estado_key(modo, carga, regimen)` | Llave de `dim_estado_operativo` por fórmula: `idx(modo)·12 + idx(carga)·3 + idx(régimen)` |
| `gold.tarifa_cop_kwh(fecha, tipo, franja)` | Tarifa vigente; antes de la primera vigencia usa la más antigua (supuesto: la tarifa de abril de 2026 se aplica a todo el histórico) |

`dim_actividad_computo` también usa una fórmula fija: `actividad_key = 1 + 4·gpu + ws1 + 2·ws2` (0 = sin bitácora).

## Vistas de indicadores

| Vista | Indicadores | Pregunta |
|---|---|---|
| `gold.v_kpi_mensual` | K1–K11 por inversor y mes | P1, P2, P3 |
| `gold.v_costo_franja_mensual` | K12 (punta / fuera de punta) | P4 |
| `gold.v_estado_actual` | O1–O4: último minuto de cada inversor | P5, P6, P7 |
| `gold.v_solarbi_perfil` | S1–S4 por tipo de tarea y modelo | P8, P9, P11 |
| `gold.v_solarbi_hora` | S5 y carga/FV/red por hora y actividad | P10 |

Las vistas de Power BI filtran `origen = 'historico'`; `v_estado_actual` también ve las filas del simulador.

## Consultas (`consultas/`, se ejecutan a mano)

- `01_negocio.sql`: una consulta por pregunta de negocio (P1–P11), la comparación antes y después de los
  cambios de configuración (SCD 2) y la conciliación contra los contadores del inversor.
- `02_json.sql`: nueve consultas sobre `bronze.context` con `->`, `->>`, `@>`, `?`, `?|`, `@?` (JSONPath),
  `jsonb_object_keys`, `jsonb_typeof` y el operador `-` para quitar campos personales (Ley 1581).

## Cómo se probó

Con un contenedor `postgres:16.15-alpine` desechable: los 7 scripts se ejecutaron al arrancar, otra vez a
mano (sin errores ni duplicados) y se cargaron las 25 178 filas reales de `context`. Las consultas JSON
devuelven datos reales. Las vistas se verificaron con un día sintético, y los KPI coinciden con el cálculo a
mano (p. ej. autosuficiencia = 1 − 4,32 / 7,2 = 40 %).
