"""Carga en PostgreSQL: Bronze (context), Silver (COPY) y Gold (cargar_gold.sql), más la conciliación."""
import time
from pathlib import Path

import pandas as pd

from transformar import a_timestamp

SQL_GOLD = Path(__file__).with_name("cargar_gold.sql")

COLS_LECTURA = ["inversor_id", "ts_minuto", "fecha_local", "minuto_dia", "n_lecturas", "n_lecturas_validas",
                "segundos_cubiertos", "e_fv_wh", "e_carga_wh", "e_red_wh", "e_bat_carga_wh", "e_bat_descarga_wh",
                "p_fv_w", "p_carga_w", "p_red_w", "p_carga_max_w", "soc_pct", "soc_min_pct", "v_bateria_v",
                "v_red_v", "temp_max_c", "modo_salida_cod", "estado_carga_cod", "regimen_red", "actividad_key",
                "es_horario_solar"]
COLS_VERSION = ["inversor_id", "nombre", "cargas", "firmware_build", "version_lib", "prioridad_salida",
                "prioridad_carga", "potencia_max_red_w", "capacidad_bateria_ah", "soc_alarma_pct",
                "soc_corte_pct", "vigente_desde", "vigente_hasta"]


def copiar(cur, tabla, df, columnas):
    """COPY desde un CSV en memoria (mucho más rápido que INSERT fila a fila)."""
    csv = df[columnas].to_csv(index=False, header=False, na_rep="")
    lista = ", ".join(f'"{c}"' for c in columnas)
    with cur.copy(f"COPY {tabla} ({lista}) FROM STDIN WITH (FORMAT csv)") as cp:
        cp.write(csv)
    print(f"  {tabla}: {len(df):,} filas")


def cargar_bronze_silver(cur, ctx_raw, ctx, minutos, estad, cfg_dia, ev):
    cur.execute("TRUNCATE bronze.context, silver.lectura_minuto, silver.estadistica_diaria, "
                "silver.config_diaria, silver.contexto, silver.evento")
    copiar(cur, "bronze.context", ctx_raw, ["id", "recorded", "start", "end", "value"])

    c = ctx.assign(contexto_id=ctx.id, ts_registro=a_timestamp(ctx.recorded),
                   ts_inicio=a_timestamp(ctx.start), ts_fin=a_timestamp(ctx.end))
    copiar(cur, "silver.contexto", c, ["contexto_id", "ts_registro", "ts_inicio", "ts_fin", "fuente",
                                       "dispositivo", "inversor_id", "tipo_contexto", "atributos"])
    copiar(cur, "silver.lectura_minuto", minutos.assign(ts_minuto=a_timestamp(minutos.ts_minuto)), COLS_LECTURA)
    copiar(cur, "silver.estadistica_diaria", estad, list(estad.columns))
    copiar(cur, "silver.config_diaria", cfg_dia, list(cfg_dia.columns))
    copiar(cur, "silver.evento", ev.assign(ts_inicio=a_timestamp(ev.ts_inicio), ts_fin=a_timestamp(ev.ts_fin)),
           ["inversor_id", "codigo", "ts_inicio", "ts_fin", "valor_referencia", "dispositivo", "detalle", "origen_id"])
    # Sin estadísticas el planificador elige malos planes para las tablas recién cargadas
    cur.execute("ANALYZE bronze.context, silver.lectura_minuto, silver.estadistica_diaria, "
                "silver.config_diaria, silver.contexto, silver.evento")


def cargar_gold(cur, versiones):
    cur.execute("""CREATE TEMP TABLE tmp_versiones (
        inversor_id smallint, nombre text, cargas text, firmware_build text, version_lib text,
        prioridad_salida smallint, prioridad_carga smallint, potencia_max_red_w integer,
        capacidad_bateria_ah integer, soc_alarma_pct smallint, soc_corte_pct smallint,
        vigente_desde date, vigente_hasta date) ON COMMIT DROP""")
    copiar(cur, "tmp_versiones", versiones, COLS_VERSION)

    texto = SQL_GOLD.read_text(encoding="utf-8")
    for bloque in texto.split("-- @paso ")[1:]:
        nombre, sql = bloque.split("\n", 1)
        t = time.time()
        cur.execute(sql)
        print(f"  gold · {nombre.split(':')[0]}: {time.time() - t:.1f} s")


def conciliar(cur, sqlite, minutos_fuente, ctx, fallas_fuente):
    """Totales de la fuente frente a lo cargado (§4 E). Devuelve filas para silver.conciliacion."""
    filas = []

    def agregar(metrica, inv, fuente, cargado, explicacion):
        filas.append((metrica, int(inv), float(fuente or 0), float(cargado or 0), explicacion))

    lect_fuente = dict(sqlite.execute("SELECT inverter, count(*) FROM analog_measurements GROUP BY 1").fetchall())
    cur.execute("SELECT inversor_id, sum(n_lecturas), count(*) FROM gold.fact_energia_minuto "
                "WHERE origen = 'historico' GROUP BY 1")
    for inv, lecturas, minutos in cur.fetchall():
        agregar("lecturas", inv, lect_fuente.get(inv), lecturas,
                "Cada fila de analog_measurements queda contada en n_lecturas (también las inválidas)")
        agregar("minutos_con_lectura", inv, minutos_fuente.get(inv), minutos,
                "Un minuto de Gold por cada minuto con al menos una lectura en la fuente")

    # Energía: contador del inversor (oficial) vs. integración de las lecturas,
    # en todos los días y solo en los días con cobertura >= 95 % (donde debe cuadrar)
    for sufijo, filtro, explicacion in (
            ("", "true",
             "Todos los días. La integración solo cubre los minutos con lecturas (huecos ~11 % del tiempo, sin "
             "extrapolar); el contador del inversor no tiene huecos. Por eso los KPI usan el contador"),
            ("_dias_completos", "disponibilidad_pct >= 95",
             "Solo días con cobertura >= 95 %: aquí la integración valida el contador")):
        cur.execute(f"""SELECT inversor_id,
                              sum(e_fv_kwh_contador), sum(e_fv_kwh),
                              sum(e_consumo_kwh_contador), sum(e_carga_kwh),
                              sum(e_red_carga_kwh_contador + e_red_bateria_kwh_contador), sum(e_red_kwh)
                         FROM gold.fact_energia_diaria
                        WHERE e_fv_kwh_contador IS NOT NULL AND {filtro}
                        GROUP BY 1""")
        for inv, fv_c, fv, car_c, car, red_c, red in cur.fetchall():
            agregar("energia_fv_kwh" + sufijo, inv, fv_c, fv, explicacion)
            agregar("energia_carga_kwh" + sufijo, inv, car_c, car, explicacion)
            agregar("energia_red_kwh" + sufijo, inv, red_c, red, explicacion + ". La red integrada (linepowerw_a) "
                    "incluye las pérdidas del cargador, que los contadores red→carga + red→batería no cuentan")

    total_ctx = sqlite.execute("SELECT count(*) FROM context").fetchone()[0]
    cur.execute("SELECT count(*) FROM bronze.context")
    agregar("registros_contexto", 0, total_ctx, cur.fetchone()[0], "Copia 1:1 de context en bronze.context")

    cur.execute("SELECT count(*) FROM gold.fact_tarea_computo")
    tareas = ctx.tipo_contexto.isin(["gpu_cnn_training_workload", "cpu_compilation_workload"]).sum()
    agregar("tareas_computo", 1, tareas, cur.fetchone()[0], "Una fila de fact_tarea_computo por tarea de las bitácoras")

    cur.execute("""SELECT e.inversor_id, count(*) FROM gold.fact_evento_operativo e
                     JOIN gold.dim_tipo_evento t USING (tipo_evento_key)
                    WHERE t.codigo LIKE 'FALLA\\_%' GROUP BY 1""")
    for inv, n in cur.fetchall():
        agregar("fallas_unicas", inv, fallas_fuente.get(inv), n,
                "Fallas únicas (inversor, código, hora) del historial desde el inicio del calendario")
    return filas


def imprimir_conciliacion(filas):
    print(f"  {'métrica':<34}{'inv':>4}{'fuente':>14}{'cargado':>14}{'dif %':>9}")
    for metrica, inv, fuente, cargado, _ in filas:
        dif = (cargado - fuente) / fuente * 100 if fuente else 0
        print(f"  {metrica:<34}{inv:>4}{fuente:>14,.1f}{cargado:>14,.1f}{dif:>8.2f}%")


def resumen_gold(cur):
    cur.execute("""SELECT 'fact_energia_minuto', count(*) FROM gold.fact_energia_minuto
         UNION ALL SELECT 'fact_energia_diaria', count(*) FROM gold.fact_energia_diaria
         UNION ALL SELECT 'fact_evento_operativo', count(*) FROM gold.fact_evento_operativo
         UNION ALL SELECT 'fact_tarea_computo', count(*) FROM gold.fact_tarea_computo
         UNION ALL SELECT 'dim_inversor', count(*) FROM gold.dim_inversor
         UNION ALL SELECT 'dim_perfil_tarea', count(*) FROM gold.dim_perfil_tarea
         UNION ALL SELECT 'dim_tipo_evento', count(*) FROM gold.dim_tipo_evento""")
    return dict(cur.fetchall())


def a_fecha(serie):
    return pd.to_datetime(serie).dt.date
