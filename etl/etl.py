"""ETL de la microrred: OpenCEM (SQLite) → PostgreSQL (Bronze, Silver, Gold).

Uso:
    python etl/etl.py

Lee la configuración de variables de entorno (ver config.py y .env.example).
Corre una vez, termina y deja evidencia en silver.etl_ejecucion, silver.calidad_log y
silver.conciliacion. Es idempotente: si se ejecuta dos veces, el resultado no cambia.
Código de salida 0 = éxito, 1 = falla (así lo interpreta el Job de Kubernetes).
"""
import sys
import time
import traceback
from contextlib import contextmanager

import psycopg

import cargar
import fuente
import transformar as tr
from calidad import BitacoraCalidad
from config import VERSION_ETL, leer_config


@contextmanager
def paso(nombre):
    print(f"\n▶ {nombre}")
    t = time.time()
    yield
    print(f"  ({time.time() - t:.1f} s)")


def ejecutar(cfg, bit):
    sqlite = fuente.conectar(cfg.sqlite)
    sha = None
    if cfg.calcular_sha256:
        with paso("Huella SHA-256 de la fuente (linaje)"):
            sha = fuente.sha256(cfg.sqlite)
            print(f"  {sha}")

    with paso("Extracción y limpieza de context (JSON)"):
        ctx_raw = fuente.contexto(sqlite)
        ctx = tr.parsear_contexto(ctx_raw, bit)

    with paso("Extracción y limpieza de lecturas"):
        med = fuente.mediciones(sqlite)
        print(f"  {len(med):,} lecturas leídas")
        med = tr.limpiar_mediciones(med, cfg, bit)
        est = tr.estados_por_minuto(fuente.estados(sqlite), bit)

    with paso("Integración a energía y agregación a 1 minuto"):
        minutos, validas = tr.lecturas_a_minutos(med, est, cfg, bit)
        minutos_fuente = med.groupby("inverter").ts_minuto.nunique().to_dict()
        del med, est
        minutos = tr.actividad_y_sol(minutos, ctx)
        print(f"  {len(minutos):,} minutos; actividad: {minutos.actividad_key.value_counts().sort_index().to_dict()}")

    with paso("Contadores diarios y configuración (SCD 2)"):
        estad = fuente.estadistica_diaria(sqlite)
        estad["fecha_local"] = cargar.a_fecha(estad.fecha_local)
        estad = tr.validar_contadores(estad, minutos, bit)
        cfg_dia = tr.config_diaria(fuente.conteos_configuracion(sqlite))
        versiones = tr.versiones_scd(cfg_dia, cfg, bit, fuente.filas_settings(sqlite))
        print(versiones[["inversor_id", "vigente_desde", "vigente_hasta", "firmware_build", "prioridad_salida",
                         "prioridad_carga", "potencia_max_red_w", "capacidad_bateria_ah"]].to_string(index=False))

    with paso("Detección de eventos"):
        fallas = fuente.fallas_unicas(sqlite)
        ev = tr.eventos(minutos, validas, fallas, ctx, cfg, bit)
        f = fallas[0]
        codigos = f.registro.str.extract(r"^\[(\d+)")[0]
        en_ventana = f.assign(codigo=codigos)[f.ts >= tr.CALENDARIO_DESDE_TS].dropna(subset=["codigo"])
        fallas_fuente = en_ventana.drop_duplicates(["inverter", "codigo", "ts"]).groupby("inverter").size().to_dict()

    with psycopg.connect(cfg.dsn) as con, con.cursor() as cur:
        with paso("Carga de Bronze y Silver (COPY)"):
            cargar.cargar_bronze_silver(cur, ctx_raw, ctx, minutos, estad, cfg_dia, ev)
        with paso("Carga de Gold (upsert idempotente)"):
            cargar.cargar_gold(cur, versiones)
        with paso("Conciliación"):
            conc = cargar.conciliar(cur, sqlite, minutos_fuente, ctx, fallas_fuente)
            cargar.imprimir_conciliacion(conc)
        resumen = cargar.resumen_gold(cur)
        con.commit()   # todo o nada: si algo falla antes, la base queda como estaba
    return sha, conc, resumen


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = leer_config()
    inicio = time.time()
    print(f"ETL microrred v{VERSION_ETL} · fuente {cfg.sqlite.name} · PostgreSQL {cfg.pg_host}:{cfg.pg_puerto}")

    with psycopg.connect(cfg.dsn, autocommit=True) as log:
        ejecucion_id = log.execute(
            "INSERT INTO silver.etl_ejecucion (fuente_archivo, version_etl) VALUES (%s, %s) RETURNING ejecucion_id",
            (cfg.sqlite.name, VERSION_ETL)).fetchone()[0]
    print(f"Ejecución #{ejecucion_id}")

    bit = BitacoraCalidad()
    try:
        sha, conc, resumen = ejecutar(cfg, bit)
    except Exception as e:
        traceback.print_exc()
        with psycopg.connect(cfg.dsn, autocommit=True) as log:
            log.execute("UPDATE silver.etl_ejecucion SET fin = now(), estado = 'fallida', mensaje = %s "
                        "WHERE ejecucion_id = %s", (f"{type(e).__name__}: {e}"[:2000], ejecucion_id))
        print(f"\n✗ ETL fallido (ejecución #{ejecucion_id})")
        return 1

    mensaje = " · ".join(f"{k}={v:,}" for k, v in resumen.items())
    with psycopg.connect(cfg.dsn, autocommit=True) as log, log.transaction():
        log.cursor().executemany(
            "INSERT INTO silver.calidad_log VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", bit.filas(ejecucion_id))
        log.cursor().executemany(
            "INSERT INTO silver.conciliacion (ejecucion_id, metrica, inversor_id, valor_fuente, valor_cargado, "
            "explicacion) VALUES (%s, %s, %s, %s, %s, %s)", [(ejecucion_id, *f) for f in conc])
        log.execute("UPDATE silver.etl_ejecucion SET fin = now(), estado = 'exitosa', fuente_sha256 = %s, "
                    "mensaje = %s WHERE ejecucion_id = %s", (sha, mensaje, ejecucion_id))
    print(f"\n✓ ETL exitoso (ejecución #{ejecucion_id}) en {time.time() - inicio:.0f} s")
    print("  " + mensaje)
    return 0


if __name__ == "__main__":
    sys.exit(main())
