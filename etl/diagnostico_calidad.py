"""Diagnóstico de calidad de la fuente OpenCEM (Fase 2).

Calcula las métricas que sustentan docs/02_diagnostico_fuente.md:
cadencia y huecos, nulos, valores fuera de rango, episodios de red caída,
balance de potencias y comparación de la energía integrada con los contadores diarios del inversor.

Uso:
    python etl/diagnostico_calidad.py [ruta_sqlite]
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SQLITE = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "datos/zenodo/opencem-v1.0.0.sqlite"
TZ = "Asia/Shanghai"
HUECO_S = 60  # un salto mayor a 60 s entre lecturas se considera hueco


def titulo(t):
    print(f"\n=== {t} ===")


def main():
    con = sqlite3.connect(f"file:{SQLITE.as_posix()}?mode=ro&immutable=1", uri=True)
    df = pd.read_sql(
        "SELECT read_ts, inverter, battvolt, battcurr, battsoc, pv1power, outw_a, linepowerw_a, "
        "linevolta, linefreq, temper1, normalloadw_a, sir, gridpowerw_a "
        "FROM analog_measurements ORDER BY inverter, read_ts", con)
    df["dia"] = pd.to_datetime(df.read_ts, unit="s", utc=True).dt.tz_convert(TZ).dt.date

    titulo("1. Cadencia y huecos por inversor")
    for inv, g in df.groupby("inverter"):
        d = g.read_ts.diff().dropna()
        print(f"Inversor {inv}: filas={len(g):,}  días con datos={g.dia.nunique()}  "
              f"cadencia mediana={d.median():.1f}s  p95={d.quantile(.95):.1f}s  "
              f"huecos>{HUECO_S}s={int((d > HUECO_S).sum()):,}  >1h={int((d > 3600).sum())}  "
              f">1día={int((d > 86400).sum())}  horas perdidas={d[d > HUECO_S].sum() / 3600:,.0f}")

    titulo("2. Filas sin ninguna medición (solo read_ts e inverter)")
    medidas = df.drop(columns=["read_ts", "inverter", "dia"])
    vacias = medidas.isna().all(axis=1)
    print(vacias.groupby(df.inverter).sum().to_string())

    v = df[~vacias].copy()
    titulo("3. Valores sospechosos (sobre filas con datos)")
    reglas = {
        "battvolt == 0 (batería de 48 V no puede marcar 0 V)": v.battvolt == 0,
        "battsoc fuera de 0-100": v.battsoc.notna() & ~v.battsoc.between(0, 100),
        "temper1 < 0 °C (clima subtropical)": v.temper1 < 0,
        "outw_a > 3000 W (picos aislados)": v.outw_a > 3000,
        "pv1power < 0": v.pv1power < 0,
        "linepowerw_a < 0": v.linepowerw_a < 0,
        "linevolta == 0 (red sin tensión)": v.linevolta == 0,
    }
    for nombre, m in reglas.items():
        print(f"{nombre}: {int(m.sum()):,} ({m.mean():.3%})")
    print(f"Columnas siempre en 0: {[c for c in ['normalloadw_a', 'sir'] if v[c].fillna(0).eq(0).all()]}")

    titulo("4. Episodios de red caída (linevolta == 0 sostenido)")
    for inv, g in v.groupby("inverter"):
        caida = g.linevolta.eq(0)
        ep = (caida != caida.shift()).cumsum()[caida]
        eps = g[caida].groupby(ep).read_ts.agg(["min", "max"])
        dur = eps["max"] - eps["min"]
        print(f"Inversor {inv}: episodios={len(dur):,}  >5 min={int((dur > 300).sum())}  "
              f">1 h={int((dur > 3600).sum())}  duración mediana={dur.median():.0f}s  máx={dur.max() / 3600:.1f}h")
        for a, b in eps[dur > 3600].itertuples(index=False):
            fa, fb = (pd.Timestamp(x, unit="s", tz="UTC").tz_convert(TZ) for x in (a, b))
            print(f"   {fa:%Y-%m-%d %H:%M} → {fb:%Y-%m-%d %H:%M} ({(b - a) / 3600:,.1f} h)")
    ctx = pd.read_sql("SELECT value FROM context WHERE value LIKE '%grid_unavailable_or_islanded%'", con)
    print(f"Eventos 'grid_unavailable_or_islanded' en la tabla context: {len(ctx)}")

    titulo("5. Balance de potencias: PV + red + batería(descarga) − carga [W]")
    res = v.pv1power + v.linepowerw_a + v.battvolt * v.battcurr - v.outw_a
    print("p5 / p50 / p95:", res.quantile([.05, .5, .95]).round(0).tolist(),
          "→ residuo positivo ≈ autoconsumo y pérdidas del inversor")

    titulo("6. Energía integrada vs contadores diarios del inversor (tabla statistics)")
    v["dt"] = v.groupby("inverter").read_ts.diff().shift(-1).clip(upper=HUECO_S).fillna(0)
    e = v.assign(pv=v.pv1power * v.dt / 3.6e6, carga=v.outw_a * v.dt / 3.6e6) \
         .groupby(["inverter", "dia"])[["pv", "carga"]].sum()
    st = pd.read_sql("SELECT read_ts, inverter, pvgeneratenergytoday, usedenergytoday FROM statistics", con)
    st["dia"] = pd.to_datetime(st.read_ts, unit="s", utc=True).dt.tz_convert(TZ).dt.date
    s = st.groupby(["inverter", "dia"])[["pvgeneratenergytoday", "usedenergytoday"]].max()
    j = e.join(s, how="inner")
    print(f"Días comparados: {len(j)}")
    print(f"PV integrada / contador PV (mediana): {(j.pv / j.pvgeneratenergytoday).median():.3f}")
    print(f"Carga integrada / contador consumo (mediana): {(j.carga / j.usedenergytoday).median():.3f}")
    con.close()


if __name__ == "__main__":
    main()
