"""Simulador de telemetría: alimenta Grafana con datos "en vivo".

Repite un día histórico completo (mismo minuto del día) con la hora actual y un pequeño
ruido, y lo inserta en gold.fact_energia_minuto con origen = 'simulado'. Power BI ignora
estas filas; Grafana sí las ve.

Cada ejecución rellena los minutos que faltan desde el último simulado hasta ahora (máximo
MAX_MINUTOS), así sirve igual como bucle (docker compose) o como CronJob de Kubernetes.

Variables de entorno:
    PGHOST, PGPORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD   conexión
    MODO          bucle | una_vez                         (defecto: una_vez)
    INTERVALO_S   segundos entre ciclos en modo bucle      (defecto: 60)
    ESCENARIO     normal | red_caida | soc_bajo | temp_alta | sin_datos   (defecto: normal)
    RUIDO_PCT     ruido aleatorio sobre potencias y energía (defecto: 5)
    MAX_MINUTOS   minutos máximos a rellenar por ciclo      (defecto: 60)
    RETENCION_DIAS  borra filas simuladas más viejas        (defecto: 7)
"""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg

OFFSET_LOCAL = timedelta(hours=8)        # Asia/Shanghai, sin horario de verano
ESCENARIOS = {"normal", "red_caida", "soc_bajo", "temp_alta", "sin_datos"}

# Días de referencia: completos (>= 95 % de cobertura) en los dos inversores y con carga real
SQL_DIAS = """
    SELECT fecha_key FROM gold.fact_energia_diaria
     WHERE disponibilidad_pct >= 95 AND e_carga_kwh_oficial > 1
     GROUP BY fecha_key HAVING count(*) = 2
     ORDER BY fecha_key"""

SQL_INSERTAR = """
INSERT INTO gold.fact_energia_minuto (
       ts_minuto, inversor_id, fecha_key, hora_key, inversor_sk, estado_key, actividad_key,
       n_lecturas, n_lecturas_validas, segundos_cubiertos, e_fv_wh, e_carga_wh, e_red_wh,
       e_bat_carga_wh, e_bat_descarga_wh, p_fv_w, p_carga_w, p_red_w, p_carga_max_w,
       soc_pct, soc_min_pct, v_bateria_v, v_red_v, temp_max_c, es_horario_solar, origen)
SELECT %(ts)s, h.inversor_id, %(fecha_key)s, %(hora_key)s,
       gold.inversor_sk_vigente(h.inversor_id, %(fecha)s),
       CASE WHEN %(esc)s = 'red_caida' THEN gold.estado_key(2::smallint, 0::smallint, 'Isla') ELSE h.estado_key END,
       0,                                         -- sin bitácora de cómputo en vivo
       h.n_lecturas, h.n_lecturas_validas, h.segundos_cubiertos,
       round(h.e_fv_wh * r.f, 3),
       round(h.e_carga_wh * r.f, 3),
       CASE WHEN %(esc)s = 'red_caida' THEN 0 ELSE round(h.e_red_wh * r.f, 3) END,
       round(h.e_bat_carga_wh * r.f, 3),
       round(h.e_bat_descarga_wh * r.f, 3),
       round(h.p_fv_w * r.f, 1),
       round(h.p_carga_w * r.f, 1),
       CASE WHEN %(esc)s = 'red_caida' THEN 0 ELSE round(h.p_red_w * r.f, 1) END,
       h.p_carga_max_w,
       CASE WHEN %(esc)s = 'soc_bajo' THEN least(h.soc_pct, 15) ELSE h.soc_pct END,
       CASE WHEN %(esc)s = 'soc_bajo' THEN least(h.soc_min_pct, 14) ELSE h.soc_min_pct END,
       h.v_bateria_v,
       CASE WHEN %(esc)s = 'red_caida' THEN 0 ELSE h.v_red_v END,
       CASE WHEN %(esc)s = 'temp_alta' THEN 48 ELSE h.temp_max_c END,
       h.es_horario_solar,
       'simulado'
  FROM (VALUES (1::smallint), (2::smallint)) AS inv(id)
  CROSS JOIN LATERAL (                      -- el minuto de referencia o el anterior más cercano
        SELECT * FROM gold.fact_energia_minuto m
         WHERE m.origen = 'historico' AND m.inversor_id = inv.id
           AND m.fecha_key = %(ref)s AND m.hora_key <= %(hora_key)s
         ORDER BY m.hora_key DESC LIMIT 1) h
  CROSS JOIN LATERAL (SELECT (1 + (random() - 0.5) * %(ruido)s / 100.0)::numeric AS f) r
ON CONFLICT (inversor_id, ts_minuto) DO NOTHING"""


def conectar():
    dsn = (f"host={os.environ.get('PGHOST', 'localhost')} port={os.environ.get('PGPORT', '5432')} "
           f"dbname={os.environ['POSTGRES_DB']} user={os.environ['POSTGRES_USER']} "
           f"password={os.environ['POSTGRES_PASSWORD']}")
    return psycopg.connect(dsn, autocommit=True)


def ciclo(con, dias, cfg):
    ahora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    if cfg["esc"] == "sin_datos":
        print(f"{ahora:%H:%M} escenario sin_datos: no se inserta nada (dispara la alerta O4)")
        return
    ultimo = con.execute("SELECT max(ts_minuto) FROM gold.fact_energia_minuto "
                         "WHERE origen = 'simulado'").fetchone()[0]
    desde = max(ultimo + timedelta(minutes=1) if ultimo else ahora, ahora - timedelta(minutes=cfg["max"] - 1))
    n = 0
    ts = desde
    while ts <= ahora:
        local = ts + OFFSET_LOCAL
        ref = dias[local.date().toordinal() % len(dias)]     # un día de referencia fijo por día simulado
        cur = con.execute(SQL_INSERTAR, {
            "ts": ts, "fecha": local.date(), "fecha_key": int(local.strftime("%Y%m%d")),
            "hora_key": local.hour * 60 + local.minute, "ref": ref, "esc": cfg["esc"], "ruido": cfg["ruido"]})
        n += cur.rowcount
        ts += timedelta(minutes=1)
    borradas = con.execute("DELETE FROM gold.fact_energia_minuto WHERE origen = 'simulado' "
                           "AND ts_minuto < now() - make_interval(days => %s)", (cfg["retencion"],)).rowcount
    print(f"{ahora:%Y-%m-%d %H:%M} UTC · escenario {cfg['esc']} · {n} filas nuevas"
          + (f" · {borradas} viejas borradas" if borradas else ""), flush=True)


def main():
    cfg = {"modo": os.environ.get("MODO", "una_vez"),
           "intervalo": int(os.environ.get("INTERVALO_S", 60)),
           "esc": os.environ.get("ESCENARIO", "normal"),
           "ruido": float(os.environ.get("RUIDO_PCT", 5)),
           "max": int(os.environ.get("MAX_MINUTOS", 60)),
           "retencion": int(os.environ.get("RETENCION_DIAS", 7))}
    if cfg["esc"] not in ESCENARIOS:
        sys.exit(f"ESCENARIO inválido: {cfg['esc']} (opciones: {', '.join(sorted(ESCENARIOS))})")
    with conectar() as con:
        dias = [r[0] for r in con.execute(SQL_DIAS).fetchall()]
        if not dias:
            sys.exit("No hay días históricos completos: primero hay que correr el ETL")
        print(f"Simulador · modo {cfg['modo']} · {len(dias)} días de referencia", flush=True)
        while True:
            ciclo(con, dias, cfg)
            if cfg["modo"] != "bucle":
                return 0
            time.sleep(cfg["intervalo"])


if __name__ == "__main__":
    sys.exit(main())
