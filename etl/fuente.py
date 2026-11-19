"""Extracción: lee la capa Bronze (opencem-v1.0.0.sqlite) en modo solo lectura.

Las tablas grandes de configuración se agregan por día dentro de SQLite para no
traer millones de filas a memoria; las lecturas sí se traen completas porque se
integran lectura a lectura.
"""
import hashlib
import sqlite3

import pandas as pd

# Día local (UTC+8) calculado dentro de SQLite
DIA_LOCAL = "date(read_ts, 'unixepoch', '+8 hours')"

COLUMNAS_MEDIDA = ["battvolt", "battcurr", "battsoc", "pv1power", "outw_a",
                   "linepowerw_a", "linevolta", "temper1"]

SETTINGS = {  # columna fuente → nombre en silver.config_diaria
    "outpriority": "prioridad_salida",
    "chgpriority": "prioridad_carga",
    "maxlinepower": "potencia_max_red_w",
    "battpackrateah": "capacidad_bateria_ah",
    "batsoclowalarm": "soc_alarma_pct",
    "batstopsoc": "soc_corte_pct",
}


def conectar(ruta):
    if not ruta.exists():
        raise SystemExit(f"No existe la fuente {ruta} (ver datos/README.md)")
    return sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro&immutable=1", uri=True)


def sha256(ruta, bloque=8 * 1024 * 1024):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        while chunk := f.read(bloque):
            h.update(chunk)
    return h.hexdigest()


def mediciones(con):
    cols = ", ".join(COLUMNAS_MEDIDA)
    return pd.read_sql(f"SELECT read_ts, inverter, {cols} FROM analog_measurements "
                       "ORDER BY inverter, read_ts", con)


def estados(con):
    return pd.read_sql("SELECT read_ts, inverter, outstatus, chgstatus, sysalarmflag FROM status "
                       "ORDER BY inverter, read_ts", con)


def estadistica_diaria(con):
    """Máximo del día de cada contador diario del inversor (se reinicia a medianoche)."""
    return pd.read_sql(f"""
        SELECT inverter AS inversor_id, {DIA_LOCAL} AS fecha_local,
               max(pvgeneratenergytoday)  AS e_fv_kwh_contador,
               max(usedenergytoday)       AS e_consumo_kwh_contador,
               max(loadconsumlinetday)    AS e_red_carga_kwh_contador,
               max(linechgenergytday)     AS e_red_bateria_kwh_contador,
               max(batchgenergytoday)     AS e_bat_carga_kwh_contador,
               max(batdischgenergytoday)  AS e_bat_descarga_kwh_contador
          FROM statistics GROUP BY 1, 2""", con)


def _conteo_diario(con, tabla, columna):
    """Cuántas veces aparece cada valor de una columna por inversor y día (para la moda)."""
    return pd.read_sql(f"""
        SELECT inverter AS inversor_id, {DIA_LOCAL} AS fecha_local, {columna} AS valor, count(*) AS n
          FROM {tabla} WHERE {columna} IS NOT NULL AND {columna} <> '[null]'
         GROUP BY 1, 2, 3""", con)


def conteos_configuracion(con):
    """Conteos diarios de cada atributo de configuración (base del SCD 2)."""
    salida = {destino: _conteo_diario(con, "settings", fuente) for fuente, destino in SETTINGS.items()}
    salida["firmware_build"] = _conteo_diario(con, "specs", "cpubuidtime")
    salida["version_lib"] = _conteo_diario(con, "specs", "libver")
    return salida


def filas_settings(con):
    return con.execute("SELECT count(*) FROM settings").fetchone()[0]


def fallas_unicas(con):
    """Une las 32 ranuras del historial de fallas y deja cada falla (inversor, registro, hora) una vez."""
    partes = [f"SELECT inverter, faulthistoryrecord{i:02d} AS registro, faulthistoryrecord{i:02d}_time AS ts, "
              f"'{i:02d}' AS ranura FROM fault_history "
              f"WHERE faulthistoryrecord{i:02d} IS NOT NULL AND faulthistoryrecord{i:02d} <> '[null]' "
              f"AND faulthistoryrecord{i:02d}_time IS NOT NULL" for i in range(32)]
    sql = ("SELECT inverter, registro, ts, min(ranura) AS ranura FROM (" + " UNION ALL ".join(partes) +
           ") GROUP BY inverter, registro, ts")
    filas = con.execute("SELECT count(*) FROM fault_history").fetchone()[0]
    return pd.read_sql(sql, con), filas


def contexto(con):
    return pd.read_sql('SELECT id, recorded, start, "end", value FROM context ORDER BY id', con)


def ascii_a_texto(valor):
    """'[74,117,108,...]' → 'Jul  1 2025 ...'; los ceros finales se descartan."""
    if not isinstance(valor, str) or valor == "[null]":
        return None
    codigos = [int(x) for x in valor.strip("[]").split(",") if x.strip() not in ("", "null")]
    texto = "".join(chr(c) for c in codigos if c > 0).strip()
    return texto or None
