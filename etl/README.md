# etl/

Proceso en Python que lleva OpenCEM (SQLite, capa Bronze) a PostgreSQL (Bronze → Silver → Gold).
Corre una vez, termina y deja evidencia de su resultado. Es **idempotente**: dos ejecuciones dejan
exactamente los mismos datos.

## Por qué Python (pandas + psycopg)

- Lee SQLite y JSON con la biblioteca estándar; no necesita herramientas extra ni licencias.
- La integración de potencia a energía (Σ P·Δt lectura a lectura) es un cálculo vectorizado en pandas.
- `psycopg` carga con `COPY` (≈ 800 000 filas en segundos) y Gold se arma con SQL dentro de PostgreSQL.
- Corre igual en local, en Docker y como `Job` de Kubernetes (Fase 6 y 7).

## Archivos

| Archivo | Qué hace |
|---|---|
| `etl.py` | Orquesta los pasos, registra la ejecución y termina con código 0 (éxito) o 1 (falla) |
| `config.py` | Lee la configuración de variables de entorno (credenciales y umbrales) |
| `fuente.py` | Extracción de la SQLite en solo lectura (+ huella SHA-256 para el linaje) |
| `transformar.py` | Limpieza con conteos, integración a 1 minuto, actividad de cómputo, contexto sin datos personales, SCD 2 y eventos |
| `calidad.py` | Bitácora de reglas: filas antes, afectadas y después |
| `cargar.py` | `COPY` a Bronze y Silver, ejecución de `cargar_gold.sql` y conciliación |
| `cargar_gold.sql` | Silver → Gold con *upsert* por llave natural |
| `requirements.txt` | Dependencias con versión fija |
| `inventario_fuente.py`, `diagnostico_calidad.py` | Scripts de las fases 1 y 2 |

## Cómo correrlo en local

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r etl/requirements.txt   # Windows (en Linux: .venv/bin/python)
.venv/Scripts/python etl/etl.py
```

Toma las credenciales del `.env` de la raíz (copia de `.env.example`) y se conecta a `localhost:5433`.

## Variables de entorno

| Variable | Defecto | Uso |
|---|---|---|
| `PGHOST`, `PGPORT` | `localhost`, `PG_PUERTO_HOST` o 5432 | Servidor (en el clúster: `postgres`, el nombre del Service) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | — (obligatorias) | Credenciales (Secret en Kubernetes) |
| `SQLITE_PATH` | `datos/zenodo/opencem-v1.0.0.sqlite` | Fuente |
| `CALCULAR_SHA256` | `true` | Guarda la huella de la fuente en `silver.etl_ejecucion` |
| `DT_MAX_S` | 60 | Tope de Δt entre lecturas (Q3) |
| `CARGA_ATIPICA_W` | 3000 | Umbral de carga atípica (Q6) |
| `SOC_BAJO_PCT`, `TEMP_ALTA_C` | 20, 45 | Umbrales de eventos (iguales a las alertas O1 y O3) |
| `EPISODIO_MIN`, `HUECO_MIN` | 5, 10 | Duración mínima de un episodio y de un hueco de datos (min) |
| `CAPACIDAD_AH_SUPUESTA` | 200 | Capacidad de batería cuando el inversor reporta 0 Ah (Q11) |

## Evidencia que deja en la base

| Tabla | Contenido |
|---|---|
| `silver.etl_ejecucion` | Una fila por ejecución: inicio, fin, estado, huella de la fuente, resumen |
| `silver.calidad_log` | Cada regla de limpieza con filas antes, afectadas y después |
| `silver.conciliacion` | Totales de la fuente frente a lo cargado, con la explicación de cada diferencia |

Las reglas, la conciliación y las decisiones están explicadas en
[docs/06_etl_calidad.md](../docs/06_etl_calidad.md).
