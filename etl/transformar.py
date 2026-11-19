"""Transformación: Bronze → Silver.

- Limpieza de lecturas con conteos (reglas Q1–Q7 de docs/02).
- Integración de potencia a energía y agregación a 1 minuto (grano de Silver).
- Estado operativo, actividad de cómputo y horario solar de cada minuto.
- Contexto JSON parseado y sin datos personales.
- Configuración diaria y versiones del inversor (SCD tipo 2).
- Detección de eventos operativos.
"""
import json
from datetime import date

import numpy as np
import pandas as pd

from config import OFFSET_LOCAL_S
from fuente import COLUMNAS_MEDIDA, ascii_a_texto

CALENDARIO_DESDE = date(2025, 7, 1)          # primer día de gold.dim_fecha
CALENDARIO_DESDE_TS = (pd.Timestamp(CALENDARIO_DESDE).value // 10**9) - OFFSET_LOCAL_S
TIPOS_TAREA = {"gpu_cnn_training_workload": "Entrenamiento GPU",
               "cpu_compilation_workload": "Compilación CPU"}
# Claves que pueden revelar personas, rutas o hábitos (Ley 1581 de 2012). Se quitan en cualquier nivel del JSON.
CLAVES_PRIVADAS = {"command", "directory", "example_commands_redacted", "command_hints_redacted",
                   "command_families", "sanitized_message", "sample_sanitized_message", "sample_record_ids",
                   "cwd_redacted", "legacy_raw_excerpt_redacted", "device_path_redacted",
                   "service_names_redacted", "record_id"}
CLAVES_EXTRAIDAS = {"source", "device", "inverter", "context_type"}   # pasan a columnas propias


# ============================================================== utilidades
def fecha_local(ts):
    """Segundos Unix UTC → fecha local del sitio."""
    return pd.to_datetime((np.asarray(ts, dtype="int64") + OFFSET_LOCAL_S) // 86400, unit="D").date


def a_timestamp(ts):
    return pd.to_datetime(ts, unit="s", utc=True)


def _moda(df, claves, col):
    """Valor más frecuente de col por grupo; en empate gana el mayor (determinista → idempotente)."""
    t = (df.dropna(subset=[col]).groupby(claves + [col]).size().rename("n").reset_index()
           .sort_values(claves + ["n", col], kind="stable")
           .drop_duplicates(claves, keep="last"))
    return t.set_index(claves)[col]


def _cubiertos(minutos_ts, inicios, fines):
    """True si el minuto que empieza en minutos_ts se cruza con algún intervalo [inicio, fin]."""
    minutos_ts = np.asarray(minutos_ts, dtype="int64")
    if len(inicios) == 0 or len(minutos_ts) == 0:
        return np.zeros(len(minutos_ts), dtype=bool)
    im = minutos_ts // 60
    a = np.asarray(inicios, dtype="int64") // 60
    b = np.asarray(fines, dtype="int64") // 60
    base, tope = min(im.min(), a.min()), max(im.max(), b.max())
    diff = np.zeros(tope - base + 2, dtype="int32")
    np.add.at(diff, a - base, 1)          # el intervalo empieza
    np.add.at(diff, b - base + 1, -1)     # y termina después de su último minuto
    return np.cumsum(diff)[im - base] > 0


# ============================================================== lecturas
def limpiar_mediciones(df, cfg, bit):
    tabla = "analog_measurements"
    total = len(df)
    vacia = df[COLUMNAS_MEDIDA].isna().all(axis=1)
    bit.registrar("Q1", "Filas sin ninguna medición (falla de comunicación): cuentan como no disponibles",
                  tabla, total, vacia.sum(), total - vacia.sum(), "descartar")
    quedan = total - vacia.sum()
    bat0 = ~vacia & (df.battvolt == 0)
    bit.registrar("Q4", "Batería a 0 V (imposible con el inversor encendido)",
                  tabla, quedan, bat0.sum(), quedan - bat0.sum(), "descartar")
    df["valida"] = ~(vacia | bat0)
    v = df.valida
    nv = int(v.sum())

    nulos = v & df[COLUMNAS_MEDIDA].isna().any(axis=1)
    bit.registrar("Q2", "Nulos sueltos: la lectura sigue, la variable nula no entra al cálculo",
                  tabla, nv, nulos.sum(), nv, "marcar")
    frio = v & (df.temper1 < 0)
    df.loc[frio, "temper1"] = np.nan
    bit.registrar("Q5", "Temperatura interna < 0 °C (clima subtropical)", tabla, nv, frio.sum(), nv, "anular")
    pico = v & (df.outw_a > cfg.carga_atipica_w)
    bit.registrar("Q6", f"Carga > {cfg.carga_atipica_w:.0f} W: atípica pero posible, se conserva",
                  tabla, nv, pico.sum(), nv, "marcar")
    negativa = v & (df.linepowerw_a < 0)
    df.loc[negativa, "linepowerw_a"] = 0.0
    bit.registrar("Q7", "Potencia de red negativa (ruido, no hay exportación)", tabla, nv, negativa.sum(), nv, "recortar")
    neg_fv = v & (df.pv1power < 0)
    df.loc[neg_fv, "pv1power"] = 0.0
    neg_carga = v & (df.outw_a < 0)
    df.loc[neg_carga, "outw_a"] = 0.0
    if neg_fv.sum() or neg_carga.sum():
        bit.registrar("Q7b", "Potencia FV o de carga negativa (ruido)", tabla, nv,
                      neg_fv.sum() + neg_carga.sum(), nv, "recortar")
    return df


def estados_por_minuto(st, bit):
    st["ts_minuto"] = (st.read_ts // 60 * 60).astype("int64")
    bandera = st.sysalarmflag.where(st.sysalarmflag.notna() & (st.sysalarmflag != "[null]"))
    sin_alarma = bandera.str.fullmatch(r"\[(0,)*0\]")
    st["bandera"] = np.where(bandera.isna(), None, np.where(sin_alarma, "OK", bandera))
    claves = ["inverter", "ts_minuto"]
    salida = pd.concat([_moda(st, claves, "outstatus").rename("modo_salida_cod"),
                        _moda(st, claves, "chgstatus").rename("estado_carga_cod"),
                        _moda(st, claves, "bandera")], axis=1)
    sin_estado = st.outstatus.isna().sum()
    bit.registrar("Q9", "Lecturas de estado sin modo de salida: el minuto queda 'Sin dato'",
                  "status", len(st), sin_estado, len(st), "marcar")
    return salida


def lecturas_a_minutos(df, estados_min, cfg, bit):
    """Integra P·Δt lectura a lectura y agrega a un minuto (UTC) por inversor."""
    df["ts_minuto"] = (df.read_ts // 60 * 60).astype("int64")
    claves = ["inverter", "ts_minuto"]
    recibidas = df.groupby(claves).size().rename("n_lecturas")

    v = df[df.valida].copy()
    siguiente = v.groupby("inverter").read_ts.shift(-1)
    dt = siguiente - v.read_ts
    bit.registrar("Q3", f"Huecos > {cfg.dt_max_s:.0f} s entre lecturas: Δt se limita, no se extrapola",
                  "analog_measurements", len(v), (dt > cfg.dt_max_s).sum(), len(v), "recortar")
    v["dt"] = dt.clip(upper=cfg.dt_max_s).fillna(0)
    h = v.dt / 3600
    p_bat = v.battvolt * v.battcurr                      # + descarga, − carga
    v["e_fv_wh"] = v.pv1power * h
    v["e_carga_wh"] = v.outw_a * h
    v["e_red_wh"] = v.linepowerw_a * h                   # ya recortada a ≥ 0 (Q7)
    v["e_bat_carga_wh"] = (-p_bat).clip(lower=0) * h
    v["e_bat_descarga_wh"] = p_bat.clip(lower=0) * h
    v["red_on"] = (v.linevolta > 0).astype(float).where(v.linevolta.notna())

    g = v.groupby(claves)
    m = pd.concat([
        g.size().rename("n_lecturas_validas"),
        g[["dt", "e_fv_wh", "e_carga_wh", "e_red_wh", "e_bat_carga_wh", "e_bat_descarga_wh"]].sum(min_count=1),
        g[["pv1power", "outw_a", "linepowerw_a", "battsoc", "battvolt", "linevolta", "red_on"]].mean()
            .rename(columns={"pv1power": "p_fv_w", "outw_a": "p_carga_w", "linepowerw_a": "p_red_w",
                             "battsoc": "soc_pct", "battvolt": "v_bateria_v", "linevolta": "v_red_v"}),
        g.outw_a.max().rename("p_carga_max_w"),
        g.battsoc.min().rename("soc_min_pct"),
        g.temper1.max().rename("temp_max_c"),
    ], axis=1)
    m = recibidas.to_frame().join(m, how="left").join(estados_min, how="left").reset_index()
    bit.registrar("A1", "Agregación de lecturas a 1 minuto por inversor (grano de Silver)",
                  "analog_measurements", len(df), len(df) - len(m), len(m), "agregar")

    m["n_lecturas_validas"] = m.n_lecturas_validas.fillna(0).astype("int64")
    m["segundos_cubiertos"] = m.pop("dt").fillna(0).clip(upper=60).round(1)
    m["regimen_red"] = np.select([m.red_on.isna(), m.red_on >= 0.5], ["Sin dato", "Conectado"], "Isla")
    m["inversor_id"] = m.pop("inverter").astype("int64")
    m["fecha_local"] = fecha_local(m.ts_minuto)
    m["minuto_dia"] = ((m.ts_minuto + OFFSET_LOCAL_S) % 86400) // 60
    for c in ("p_carga_max_w", "modo_salida_cod", "estado_carga_cod"):
        m[c] = m[c].round().astype("Int64")
    for c in ("e_fv_wh", "e_carga_wh", "e_red_wh", "e_bat_carga_wh", "e_bat_descarga_wh"):
        m[c] = m[c].round(3)
    for c, d in (("p_fv_w", 1), ("p_carga_w", 1), ("p_red_w", 1), ("soc_pct", 1), ("soc_min_pct", 1),
                 ("v_bateria_v", 2), ("v_red_v", 2), ("temp_max_c", 1)):
        m[c] = m[c].round(d)
    return m, v[["inverter", "read_ts"]]


def actividad_y_sol(m, ctx):
    """actividad_key = 1 + 4·gpu + ws1 + 2·ws2 dentro de la ventana de bitácoras del inversor 1; 0 fuera."""
    ts = m.ts_minuto.to_numpy()
    tareas = ctx[ctx.tipo_contexto.isin(TIPOS_TAREA) & (ctx.inversor_id == 1)]

    def activos(filtro):
        t = tareas[filtro]
        return _cubiertos(ts, t.start, t.end).astype(int)

    gpu = activos(tareas.tipo_contexto == "gpu_cnn_training_workload")
    cpu = tareas.tipo_contexto == "cpu_compilation_workload"
    ws1 = activos(cpu & (tareas.dispositivo == "workstation1"))
    ws2 = activos(cpu & (tareas.dispositivo == "workstation2"))
    desde, hasta = tareas.start.min() // 60 * 60, tareas.end.max() // 60 * 60
    en_ventana = (m.inversor_id.to_numpy() == 1) & (ts >= desde) & (ts <= hasta)
    m["actividad_key"] = np.where(en_ventana, 1 + 4 * gpu + ws1 + 2 * ws2, 0)

    sol = ctx[ctx.tipo_contexto == "solar_daylight"]
    dias_con_dato = set(pd.to_datetime(sol.valor.map(lambda v: v.get("local_date"))).dt.date)
    dentro = _cubiertos(ts, sol.start, sol.end)
    con_dato = m.fecha_local.isin(dias_con_dato).to_numpy()
    m["es_horario_solar"] = pd.array(np.where(con_dato, dentro, False), dtype="boolean")
    m.loc[~con_dato, "es_horario_solar"] = pd.NA
    return m


# ============================================================== contadores diarios del inversor
CONTADORES = ["e_fv_kwh_contador", "e_consumo_kwh_contador", "e_red_carga_kwh_contador",
              "e_red_bateria_kwh_contador", "e_bat_carga_kwh_contador", "e_bat_descarga_kwh_contador"]


def validar_contadores(estad, m, bit):
    """D2: anula los contadores de un día que contradicen las lecturas de ese mismo día.

    Se compara el consumo del contador con la carga integrada llevada a 24 h (solo como prueba,
    no como dato). Incoherente = cobertura >= 50 %, diferencia > 2 kWh y razón fuera de [0,5; 2].
    Caso real: tras el apagado por tifón (sep-2025) el inversor 1 reportó por semanas contadores
    casi iguales a los del inversor 2 (~25 kWh/día) mientras sus lecturas daban ~3 kWh/día.
    """
    dia = (m.groupby(["inversor_id", "fecha_local"])
             .agg(e_wh=("e_carga_wh", "sum"), seg=("segundos_cubiertos", "sum")).reset_index())
    x = estad.merge(dia, on=["inversor_id", "fecha_local"], how="left")
    escalada = x.e_wh / 1000 * 86400 / x.seg
    cont = x.e_consumo_kwh_contador
    incoherente = ((x.seg / 864 >= 50) & ((cont - escalada).abs() > 2)
                   & ((cont > 2 * escalada) | (cont < 0.5 * escalada))).to_numpy()
    estad.loc[incoherente, CONTADORES] = np.nan
    bit.registrar("D2", "Contadores diarios que contradicen las lecturas del mismo día (p. ej. tras el tifón)",
                  "statistics", len(estad), incoherente.sum(), len(estad), "anular")

    completos = estad.dropna(subset=CONTADORES)[["inversor_id", "fecha_local"]].assign(hay=True)
    dias = dia[["inversor_id", "fecha_local"]]
    sin = dias.merge(completos, how="left", on=["inversor_id", "fecha_local"]).hay.isna().sum()
    bit.registrar("D1", "Días con lecturas pero sin contador válido: la energía oficial es la integrada",
                  "statistics", len(dias), sin, len(dias), "imputar")
    return estad


# ============================================================== contexto JSON
def _sin_privados(obj):
    if isinstance(obj, dict):
        return {k: _sin_privados(v) for k, v in obj.items() if k not in CLAVES_PRIVADAS}
    if isinstance(obj, list):
        return [_sin_privados(x) for x in obj]
    return obj


def _tiene_privados(obj):
    if isinstance(obj, dict):
        return any(k in CLAVES_PRIVADAS or _tiene_privados(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_tiene_privados(x) for x in obj)
    return False


def parsear_contexto(raw, bit):
    valores = raw.value.map(json.loads)
    ctx = raw[["id", "recorded", "start", "end"]].copy()
    ctx["valor"] = valores
    ctx["fuente"] = valores.map(lambda v: v.get("source"))
    ctx["dispositivo"] = valores.map(lambda v: v.get("device"))
    ctx["inversor_id"] = pd.to_numeric(valores.map(lambda v: v.get("inverter")), errors="coerce").astype("Int64")
    ctx["tipo_contexto"] = valores.map(
        lambda v: v.get("context_type") or ("manual_entry" if v.get("source") == "manual entry" else "sin_tipo"))

    privados = valores.map(_tiene_privados)
    ctx["atributos"] = valores.map(lambda v: json.dumps(
        {k: x for k, x in _sin_privados(v).items() if k not in CLAVES_EXTRAIDAS}, ensure_ascii=False))
    bit.registrar("C1", "Claves con datos personales (comandos, rutas, mensajes de Windows) en cualquier nivel del JSON",
                  "context", len(ctx), privados.sum(), len(ctx), "anular")

    invertidos = ctx.end < ctx.start
    ctx.loc[invertidos, "end"] = ctx.loc[invertidos, "start"]
    bit.registrar("C2", "Intervalos con fin antes del inicio", "context", len(ctx), invertidos.sum(), len(ctx), "recortar")
    return ctx


# ============================================================== configuración y SCD 2
ATRIBUTOS_SCD = ["firmware_build", "version_lib", "prioridad_salida", "prioridad_carga",
                 "potencia_max_red_w", "capacidad_bateria_ah", "soc_alarma_pct", "soc_corte_pct"]
CARGAS = {1: "Estaciones de trabajo con GPU", 2: "Climatización"}


def config_diaria(conteos):
    """Moda diaria de cada atributo: filtra el parpadeo de lecturas incompletas."""
    partes = []
    for nombre, t in conteos.items():
        moda = (t.sort_values(["inversor_id", "fecha_local", "n", "valor"], kind="stable")
                 .drop_duplicates(["inversor_id", "fecha_local"], keep="last"))
        partes.append(moda.set_index(["inversor_id", "fecha_local"]).valor.rename(nombre))
    cfg = pd.concat(partes, axis=1).reset_index()
    cfg["fecha_local"] = pd.to_datetime(cfg.fecha_local).dt.date
    cfg["firmware_build"] = cfg.firmware_build.map(ascii_a_texto)
    cfg["version_lib"] = cfg.version_lib.map(ascii_a_texto)
    for c in ATRIBUTOS_SCD[2:]:
        cfg[c] = pd.to_numeric(cfg[c], errors="coerce").round().astype("Int64")
    return cfg.sort_values(["inversor_id", "fecha_local"]).reset_index(drop=True)


def versiones_scd(cfg_dia, cfg, bit, filas_settings, dias_min=3):
    """Nueva versión solo si la moda diaria cambia y se mantiene >= dias_min días seguidos."""
    versiones = []
    for inv, g in cfg_dia.groupby("inversor_id"):
        g = g.sort_values("fecha_local").copy()
        g[ATRIBUTOS_SCD] = g[ATRIBUTOS_SCD].ffill().bfill()   # specs termina el 2026-02-03
        cero = (g.capacidad_bateria_ah == 0).sum()
        if cero:
            g["capacidad_bateria_ah"] = g.capacidad_bateria_ah.replace(0, cfg.capacidad_ah_supuesta)
            bit.registrar("Q11", f"Capacidad de batería 0 Ah en el inversor {inv}: se asume "
                                 f"{cfg.capacidad_ah_supuesta} Ah", "settings", len(g), cero, len(g), "imputar")
        tramos = []   # [primer día, atributos, días]
        for fila in g.itertuples(index=False):
            tup = tuple(None if pd.isna(getattr(fila, a)) else getattr(fila, a) for a in ATRIBUTOS_SCD)
            if tramos and tramos[-1][1] == tup:
                tramos[-1][2] += 1
            else:
                tramos.append([fila.fecha_local, tup, 1])
        vigentes = [[CALENDARIO_DESDE, tramos[0][1]]]
        for inicio, tup, dias in tramos[1:]:
            if tup != vigentes[-1][1] and dias >= dias_min:
                vigentes.append([inicio, tup])
        for i, (desde, tup) in enumerate(vigentes):
            hasta = (pd.Timestamp(vigentes[i + 1][0]) - pd.Timedelta(days=1)).date() \
                if i + 1 < len(vigentes) else date(9999, 12, 31)
            versiones.append({"inversor_id": int(inv), "nombre": f"Inversor {inv}", "cargas": CARGAS.get(int(inv)),
                              **dict(zip(ATRIBUTOS_SCD, tup)), "vigente_desde": desde, "vigente_hasta": hasta})
    ver = pd.DataFrame(versiones)
    bit.registrar("S1", "Configuración: lecturas de settings → versiones del inversor (SCD 2, cambios >= 3 días)",
                  "settings", filas_settings, filas_settings - len(ver), len(ver), "agregar")
    return ver


# ============================================================== eventos
def _episodios(m, mascara, gap_s, min_s, valor=None, fn=None, extra=None):
    """Agrupa minutos consecutivos donde mascara es verdadera. Un hueco > gap_s corta el episodio."""
    m = m.reset_index(drop=True)
    mascara = mascara.reset_index(drop=True)
    corte = (mascara != mascara.shift()) | (m.ts_minuto.diff() > gap_s)
    if extra is not None:
        extra = extra.reset_index(drop=True)
        corte |= extra != extra.shift()
    m = m.assign(grupo=corte.cumsum())[mascara]
    if m.empty:
        return pd.DataFrame(columns=["ts_inicio", "ts_fin", "valor_referencia", "minutos", "extra"])
    agg = {"ts_inicio": ("ts_minuto", "min"), "ts_fin": ("ts_minuto", "max"), "minutos": ("ts_minuto", "size")}
    if valor:
        agg["valor_referencia"] = (valor, fn)
    if extra is not None:
        m = m.assign(extra=extra[m.index])
        agg["extra"] = ("extra", "first")
    ep = m.groupby("grupo").agg(**agg).reset_index(drop=True)
    ep["ts_fin"] += 60
    return ep[(ep.ts_fin - ep.ts_inicio) >= min_s]


def eventos(m, validas, fallas, ctx, cfg, bit):
    gap = cfg.hueco_min * 60
    min_ep = cfg.episodio_min * 60
    filas = []

    def agregar(ep, inv, codigo, detalle=None):
        for r in ep.itertuples(index=False):
            d = detalle(r) if detalle else {"minutos_con_dato": int(r.minutos)}
            filas.append({"inversor_id": inv, "codigo": codigo, "ts_inicio": r.ts_inicio, "ts_fin": r.ts_fin,
                          "valor_referencia": getattr(r, "valor_referencia", None), "dispositivo": "inverter",
                          "detalle": json.dumps(d), "origen_id": "telemetria"})

    for inv, g in m.groupby("inversor_id"):
        g = g.sort_values("ts_minuto")
        con_red = g[g.regimen_red != "Sin dato"]
        agregar(_episodios(con_red, con_red.regimen_red == "Isla", gap, min_ep), inv, "RED_CAIDA")
        soc = g[g.soc_pct.notna()]
        agregar(_episodios(soc, soc.soc_pct < cfg.soc_bajo_pct, gap, min_ep, "soc_min_pct", "min"), inv, "SOC_BAJO")
        temp = g[g.temp_max_c.notna()]
        agregar(_episodios(temp, temp.temp_max_c > cfg.temp_alta_c, gap, 0, "temp_max_c", "max"), inv, "TEMP_ALTA")
        ban = g[g.bandera.notna()]
        agregar(_episodios(ban, ban.bandera != "OK", gap, 0, extra=ban.bandera), inv, "ALARMA_SISTEMA",
                lambda r: {"bandera": r.extra, "minutos_con_dato": int(r.minutos)})

    # Huecos de datos: sin lecturas válidas por más de HUECO_MIN minutos
    for inv, g in validas.groupby("inverter"):
        sig = g.read_ts.shift(-1)
        h = g[(sig - g.read_ts) > gap].assign(fin=sig)
        for r in h.itertuples(index=False):
            filas.append({"inversor_id": int(inv), "codigo": "HUECO_DATOS", "ts_inicio": r.read_ts, "ts_fin": r.fin,
                          "valor_referencia": round((r.fin - r.read_ts) / 60, 1), "dispositivo": "inverter",
                          "detalle": None, "origen_id": "telemetria"})

    # Fallas del inversor (historial de 32 ranuras deduplicado)
    f, filas_fh = fallas
    bit.registrar("F1", "Historial de fallas: 32 ranuras repetidas en cada lectura → fallas únicas",
                  "fault_history", filas_fh, filas_fh - len(f), len(f), "deduplicar")
    for r in f.itertuples(index=False):
        reg = [int(x) for x in r.registro.strip("[]").split(",") if x.strip() not in ("", "null")]
        if reg:
            filas.append({"inversor_id": int(r.inverter), "codigo": f"FALLA_{reg[0]}", "ts_inicio": r.ts,
                          "ts_fin": r.ts, "valor_referencia": reg[0], "dispositivo": "inverter",
                          "detalle": json.dumps({"registro": reg}), "origen_id": f"fault_history ranura {r.ranura}"})

    # Eventos anotados en context
    for r in ctx.itertuples(index=False):
        codigo, texto = None, (r.valor.get("textual_description") or "")
        if r.tipo_contexto == "unexpected_shutdown":
            codigo = "APAGADO_INESPERADO"
        elif r.tipo_contexto == "scheduled_reboot_or_shutdown":
            codigo = "REINICIO"
        elif r.tipo_contexto == "manual_entry" and "typhoon" in texto.lower():
            codigo = "APAGADO_TIFON"
        elif r.tipo_contexto == "manual_entry" and "AC in office turned on" in texto:
            codigo = "AIRE_ON"
        elif r.tipo_contexto == "manual_entry" and "AC in office turned off" in texto:
            codigo = "AIRE_OFF"
        if codigo:
            filas.append({"inversor_id": int(r.inversor_id) if pd.notna(r.inversor_id) else 0, "codigo": codigo,
                          "ts_inicio": r.start, "ts_fin": r.end, "valor_referencia": None,
                          "dispositivo": r.dispositivo, "detalle": json.dumps({"tipo_contexto": r.tipo_contexto}),
                          "origen_id": f"context {r.id}"})

    ev = pd.DataFrame(filas)
    antes = len(ev)
    ev = ev.sort_values(["inversor_id", "codigo", "ts_inicio", "origen_id"]) \
           .drop_duplicates(["inversor_id", "codigo", "ts_inicio"])
    bit.registrar("E1", "Eventos repetidos (misma clave inversor, tipo e inicio)", "silver.evento",
                  antes, antes - len(ev), len(ev), "deduplicar")
    fuera = ev.ts_inicio < CALENDARIO_DESDE_TS
    bit.registrar("E2", f"Eventos anteriores al calendario ({CALENDARIO_DESDE}): fallas viejas del historial",
                  "silver.evento", len(ev), fuera.sum(), len(ev) - fuera.sum(), "descartar")
    ev = ev[~fuera].copy()
    ev["valor_referencia"] = pd.to_numeric(ev.valor_referencia, errors="coerce")
    print("  eventos por tipo:", ev.codigo.str.replace(r"FALLA_\d+", "FALLA_*", regex=True)
          .value_counts().to_dict())
    return ev
