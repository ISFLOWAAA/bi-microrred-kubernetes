"""Inventario de la fuente OpenCEM (capa Bronze).

Abre el .sqlite en modo solo lectura (no lo modifica) y genera un reporte en Markdown con:
tablas, número de columnas, filas, filas por inversor y periodo que cubre cada tabla.

Uso:
    python etl/inventario_fuente.py [ruta_sqlite] [ruta_salida_md]
"""
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parent.parent
SQLITE = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "datos/zenodo/opencem-v1.0.0.sqlite"
SALIDA = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "docs/01_inventario_fuente.md"
TZ_LOCAL = ZoneInfo("Asia/Shanghai")  # zona horaria del sitio (Shenzhen)


def fecha(ts):
    if ts is None:
        return "—"
    utc = datetime.fromtimestamp(ts, timezone.utc)
    return f"{utc:%Y-%m-%d %H:%M:%S} UTC ({utc.astimezone(TZ_LOCAL):%Y-%m-%d %H:%M} local)"


def contexto(con):
    """Resumen del JSON de la tabla context: fuentes, dispositivos y tipos de evento."""
    import json
    from collections import Counter
    fuente, disp, tipo = Counter(), Counter(), Counter()
    for (v,) in con.execute('SELECT value FROM "context"'):
        v = json.loads(v)
        fuente[v.get("source")] += 1
        disp[v.get("device")] += 1
        tipo[v.get("context_type")] += 1
    rec = con.execute('SELECT MIN(recorded), MAX(recorded) FROM "context"').fetchone()
    out = ["", f"- Campo `recorded` (cuándo se anotó): {fecha(rec[0])} → {fecha(rec[1])}",
           "- Campo `value`: JSON con claves comunes `source`, `device`, `inverter`, `context_type`.",
           f"- Tipos de contexto distintos: {len(tipo)}", ""]
    for titulo, cont, n in (("Fuente (`source`)", fuente, 20), ("Dispositivo (`device`)", disp, 20),
                            ("Tipo (`context_type`), 15 más frecuentes", tipo, 15)):
        out += [f"| {titulo} | Filas |", "|---|---|"]
        out += [f"| {k if k is not None else '(sin valor)'} | {c:,} |" for k, c in cont.most_common(n)]
        out += [""]
    return out


def main():
    inicio = time.time()
    con = sqlite3.connect(f"file:{SQLITE.as_posix()}?mode=ro&immutable=1", uri=True)
    tablas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    resumen, detalle = [], []
    for t in tablas:
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        filas = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]

        if "read_ts" in cols:
            ts_min, ts_max = con.execute(f'SELECT MIN(read_ts), MAX(read_ts) FROM "{t}"').fetchone()
            por_inv = con.execute(
                f'SELECT inverter, COUNT(*), MIN(read_ts), MAX(read_ts) FROM "{t}" '
                'GROUP BY inverter ORDER BY inverter').fetchall()
        else:  # tabla context: usa recorded / start / end
            ts_min, ts_max = con.execute(
                'SELECT MIN("start"), MAX("end") FROM "context"').fetchone()
            por_inv = []

        dias = (ts_max - ts_min) / 86400 if ts_min and ts_max else 0
        resumen.append(f"| `{t}` | {len(cols)} | {filas:,} | {fecha(ts_min)} | {fecha(ts_max)} | {dias:,.1f} |")

        bloque = [f"### `{t}`", "", f"- Columnas ({len(cols)}): " + ", ".join(f"`{c}`" for c in cols)]
        if por_inv:
            bloque += ["", "| Inversor | Filas | Desde | Hasta |", "|---|---|---|---|"]
            bloque += [f"| {i} | {n:,} | {fecha(a)} | {fecha(b)} |" for i, n, a, b in por_inv]
        if t == "context":
            bloque += contexto(con)
        detalle += bloque + [""]

    con.close()
    md = [
        "# Inventario de la fuente (capa Bronze)",
        "",
        f"- Archivo: `{SQLITE.name}` ({SQLITE.stat().st_size / 1e9:.2f} GB), abierto en solo lectura.",
        f"- Generado con `etl/inventario_fuente.py` el {datetime.now():%Y-%m-%d %H:%M} "
        f"en {time.time() - inicio:.0f} s.",
        "- Las marcas de tiempo de la base son segundos Unix en UTC; se muestran también en hora local "
        "del sitio (Asia/Shanghai, UTC+8).",
        "",
        "## Resumen",
        "",
        "| Tabla | Columnas | Filas | Desde | Hasta | Días |",
        "|---|---|---|---|---|---|",
        *resumen,
        "",
        "## Detalle por tabla",
        "",
        *detalle,
    ]
    SALIDA.write_text("\n".join(md), encoding="utf-8")
    print(f"Inventario escrito en {SALIDA} ({time.time() - inicio:.0f} s)")


if __name__ == "__main__":
    main()
