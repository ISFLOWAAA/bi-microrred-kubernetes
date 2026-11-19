"""Genera el informe PDF del Taller 6 a partir de los documentos del repositorio.

    python docs/generar_informe.py

Une los .md de docs/, los README de cada carpeta, las capturas (docs/img) y las evidencias del clúster
(docs/evidencias) en un solo HTML y lo imprime a PDF con Edge (Playwright). Los diagramas Mermaid se
dibujan al imprimir (necesita internet para cargar mermaid.js).
Requisitos: pip install markdown playwright
Salida: docs/BI_Taller6_Asprilla_Grisales.pdf
"""
import html
import re
from datetime import date
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
SALIDA = DOCS / "BI_Taller6_Asprilla_Grisales.pdf"
REPO = "https://github.com/ISFLOWAAA/bi-microrred-kubernetes"
MERMAID = []


def md(texto, bajar=0):
    """Markdown → HTML. Los bloques mermaid se reservan y se reinsertan sin procesar; los enlaces relativos quedan como texto."""
    def reservar(m):
        MERMAID.append(m.group(1))
        return f"\n\n@@MERMAID{len(MERMAID) - 1}@@\n\n"
    texto = re.sub(r"\A# [^\n]*\n", "", texto)                                          # el título del apartado ya lo pone la sección
    texto = re.sub(r"```mermaid\n(.*?)```", reservar, texto, flags=re.S)
    texto = re.sub(r"\[([^\]]+)\]\((?!https?://|#)[^)]+\)", r"\1", texto)           # enlaces relativos → texto
    if bajar:                                                                           # bajar el nivel de los títulos
        texto = re.sub(r"^(#{1,5}) ", lambda m: "#" * min(6, len(m.group(1)) + bajar) + " ", texto, flags=re.M)
    out = markdown.markdown(texto, extensions=["tables", "fenced_code", "sane_lists"])
    return re.sub(r"<p>@@MERMAID(\d+)@@</p>", lambda m: f'<pre class="mermaid">{MERMAID[int(m.group(1))]}</pre>', out)


def leer(ruta, desde=None):
    t = (RAIZ / ruta).read_text(encoding="utf-8")
    if desde:
        t = t[t.index(desde):]
    return t


def img(nombre, pie, ancho="100%"):
    return f'<figure><img src="img/{nombre}" style="width:{ancho}"><figcaption>{html.escape(pie)}</figcaption></figure>'


def evidencia(nombre, titulo):
    t = (DOCS / "evidencias" / nombre).read_text(encoding="utf-8")
    return f"<h3>{html.escape(titulo)}</h3><pre class='evidencia'>{html.escape(t)}</pre>"


def seccion(num, titulo, cuerpo):
    return f'<section><h1>{num}. {html.escape(titulo)}</h1>{cuerpo}</section>'


def construir():
    s = []
    # ---- 1. Resumen
    s.append(seccion(1, "Problema, enfoque y arquitectura", md(leer("README.md", "## ¿Qué es?"), 1).split("<h3>Datos y cita")[0]))
    # ---- 2. Fuente
    chk = leer("datos/README.md")
    s.append(seccion(2, "Fuente de datos: descarga, verificación e inventario", md(chk, 1) + md(leer("docs/01_inventario_fuente.md"), 1)))
    s.append(seccion(3, "Diagnóstico de calidad de la fuente (§4 A)", md(leer("docs/02_diagnostico_fuente.md"), 1)))
    s.append(seccion(4, "Negocio e indicadores (§4 A y B)", md(leer("docs/03_negocio_indicadores.md"), 1)))
    s.append(seccion(5, "Modelo dimensional (§4 C)", md(leer("docs/04_modelo_dimensional.md"), 1)))
    s.append(seccion(6, "Diccionario de datos (§4 D)", md(leer("docs/05_diccionario_datos.md"), 1)))
    s.append(seccion(7, "ETL y calidad de datos (§4 E)", md(leer("docs/06_etl_calidad.md"), 1)))
    s.append(seccion(8, "Base de datos (§4 F)", md(leer("sql/README.md"), 1)))
    # ---- 9. Contenedores y Kubernetes
    s.append(seccion(9, "Docker y Kubernetes (§4 K)", md(leer("docs/07_contenedores.md"), 1) + md(leer("k8s/README.md"), 1)))
    # ---- 10. Grafana
    s.append(seccion(10, "Grafana: tablero operativo y alertas (§4 H)", md(leer("grafana/README.md"), 1)
                     + img("grafana_operacion.png", "Tablero «Microrred · Operación», inversor 1 (datos del simulador en vivo)")
                     + img("grafana_operacion_inv2.png", "Mismo tablero con el selector en el inversor 2")
                     + img("grafana_alertas_disparada.png", "Alerta «Red caída» disparada al cambiar el simulador al escenario red_caida")
                     + img("grafana_alertas.png", "Reglas de alerta provisionadas")))
    # ---- 11. Power BI
    s.append(seccion(11, "Power BI: tablero analítico (§4 G)", md(leer("powerbi/README.md"), 1)
                     + img("powerbi_1_resumen.png", "Página 1 · Resumen ejecutivo")
                     + img("powerbi_2_balance.png", "Página 2 · Balance y batería")
                     + img("powerbi_3_solarbi.png", "Página 3 · SolarBI y escenarios (parámetros what-if)")))
    # ---- 12. Arquitectura y análisis
    s.append(seccion(12, "Arquitectura y análisis comparativo (§4 I)", md(leer("docs/08_arquitectura_analisis.md"), 1)))
    s.append(seccion(13, "Ética y seguridad (§4 J)", md(leer("docs/09_etica_seguridad.md"), 1)))
    # ---- 14. Evidencias
    ev = "<p>Salidas reales de <code>kubectl</code> sobre el clúster local (namespace <code>taller6</code>). No contienen valores de contraseñas: solo referencias al Secret.</p>"
    for n, t in (("01_kubectl_get.txt", "kubectl get: nodos, pods, servicios, volúmenes, ConfigMap, Secret y CronJob"),
                 ("02_describe_postgres.txt", "kubectl describe statefulset/postgres"),
                 ("03_describe_grafana.txt", "kubectl describe deployment/grafana"),
                 ("04_etl_job.txt", "kubectl describe job/etl-carga-historica"),
                 ("05_cronjob_simulador.txt", "kubectl describe cronjob/simulador"),
                 ("06_resiliencia.txt", "Resiliencia: se borran los pods de PostgreSQL y de Grafana")):
        ev += evidencia(n, t)
    s.append(seccion(14, "Evidencias del clúster (§4 K.4)", ev))
    s.append(seccion(15, "Hallazgos y recomendaciones", md(leer("docs/10_hallazgos.md"), 1)))
    # ---- 16. Repositorio
    repo = f"""<p>Repositorio: <b>{REPO}</b></p>
<table><tr><th>Carpeta</th><th>Contenido versionado</th></tr>
<tr><td><code>sql/</code></td><td>DDL por capas, vistas de indicadores, roles y consultas de negocio y JSON</td></tr>
<tr><td><code>etl/</code></td><td>Código del ETL, Dockerfile y requisitos con versión fija</td></tr>
<tr><td><code>simulador/</code></td><td>Simulador con escenarios de alerta y su Dockerfile</td></tr>
<tr><td><code>k8s/</code></td><td>Manifiestos YAML y los scripts <code>levantar.ps1</code> / <code>borrar.ps1</code></td></tr>
<tr><td><code>grafana/</code></td><td>Provisioning (fuente de datos, tablero, alertas)</td></tr>
<tr><td><code>powerbi/</code></td><td>Proyecto PBIP (modelo TMDL y reporte)</td></tr>
<tr><td><code>docs/</code></td><td>Documentación, evidencias, capturas y este informe</td></tr></table>
<p><b>Reproducir desde cero:</b> <code>cp .env.example .env</code> (poner contraseñas) y
<code>powershell -ExecutionPolicy Bypass -File k8s\\levantar.ps1</code>; para borrar, <code>k8s\\borrar.ps1</code>.
Ni los datos crudos ni las contraseñas están en el repositorio.</p>"""
    s.append(seccion(16, "Repositorio y reproducibilidad (§5)", repo))
    # ---- 17. English corner
    eng = """<p><i>From inverter telemetry to actionable insights: a containerized, Kubernetes-orchestrated BI pipeline for a hybrid microgrid.</i></p>
<table><tr><th>Term</th><th>In this project</th></tr>
<tr><td>hybrid microgrid</td><td>Solar panels + battery + utility grid behind two hybrid inverters</td></tr>
<tr><td>state of charge (SoC)</td><td>Battery charge level in %; alert O1 fires below 20 %</td></tr>
<tr><td>self-sufficiency</td><td>Share of consumption not imported from the grid (KPI K6)</td></tr>
<tr><td>grid import</td><td>Energy bought from the utility (KPI K3)</td></tr>
<tr><td>data lineage</td><td>Source column → rule → target column, documented in the data dictionary</td></tr>
<tr><td>idempotent load</td><td>Running the ETL twice leaves exactly the same data (proved with table fingerprints)</td></tr>
<tr><td>container image</td><td><code>taller6/etl</code> and <code>taller6/simulador</code>, built from versioned Dockerfiles</td></tr>
<tr><td>pod</td><td>Smallest deployable unit; <code>postgres-0</code>, the Grafana pod, the ETL and simulator pods</td></tr>
<tr><td>deployment</td><td>Keeps Grafana always available</td></tr>
<tr><td>persistent volume</td><td>5 Gi volume claimed by PostgreSQL so data survives restarts</td></tr>
<tr><td>secret</td><td>Holds the database and Grafana passwords outside images and Git</td></tr>
<tr><td>config map</td><td>Non-sensitive settings: thresholds, host names, SQL, Grafana provisioning</td></tr>
<tr><td>liveness probe</td><td>Restarts a container that stops answering (<code>pg_isready</code>, <code>/api/health</code>)</td></tr>
<tr><td>provisioning</td><td>Grafana data source, dashboard and alerts loaded from files at start-up</td></tr></table>"""
    s.append(seccion(17, "English corner (§8)", eng))
    return "".join(s)


CSS = """
@page { size: A4; margin: 17mm 15mm 17mm 15mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 9.6pt; line-height: 1.42; color: #1f2937; }
h1 { font-size: 19pt; color: #0f3d5e; border-bottom: 3px solid #f2b705; padding-bottom: 4px; margin: 0 0 10px; page-break-before: always; }
section:first-of-type h1 { page-break-before: auto; }
h2 { font-size: 13.5pt; color: #0f3d5e; margin: 16px 0 6px; page-break-after: avoid; }
h3 { font-size: 11pt; color: #1f4e79; margin: 12px 0 4px; page-break-after: avoid; }
h4, h5 { font-size: 10pt; margin: 8px 0 3px; page-break-after: avoid; }
p { margin: 4px 0 7px; } li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 8pt; page-break-inside: auto; }
th { background: #0f3d5e; color: #fff; text-align: left; padding: 3px 5px; }
td { border: 1px solid #d5dae1; padding: 3px 5px; vertical-align: top; }
tr { page-break-inside: avoid; } tr:nth-child(even) td { background: #f6f8fa; }
code { font-family: Consolas, 'Courier New', monospace; font-size: 8.4pt; background: #eef1f5; padding: 0 2px; border-radius: 2px; }
pre { background: #f3f5f8; border: 1px solid #dde2e8; border-radius: 4px; padding: 6px 8px; font-size: 7.6pt; line-height: 1.3; white-space: pre-wrap; word-break: break-word; page-break-inside: auto; }
pre code { background: none; padding: 0; font-size: inherit; }
pre.evidencia { font-family: Consolas, monospace; font-size: 6.9pt; background: #0f172a; color: #e5e7eb; border: none; }
pre.mermaid { background: #fff; border: 1px solid #e3e7ec; text-align: center; font-family: 'Segoe UI'; white-space: normal; page-break-inside: avoid; }
blockquote { margin: 6px 0; padding: 4px 10px; border-left: 4px solid #f2b705; background: #fff9e5; color: #4b5563; }
figure { margin: 10px 0; text-align: center; page-break-inside: avoid; } figure img { border: 1px solid #d5dae1; border-radius: 4px; }
figcaption { font-size: 8pt; color: #6b7280; margin-top: 3px; }
.portada { height: 255mm; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.portada .barra { width: 90px; height: 7px; background: #f2b705; margin-bottom: 18px; }
.portada h1 { all: unset; display: block; font-size: 30pt; font-weight: 700; color: #0f3d5e; line-height: 1.15; }
.portada .sub { font-size: 12.5pt; color: #4b5563; margin: 14px 0 34px; font-style: italic; max-width: 150mm; }
.portada table { font-size: 10.5pt; width: 150mm; } .portada td, .portada th { border: none; background: none !important; color: #1f2937; padding: 4px 0; }
.portada th { width: 42mm; color: #6b7280; font-weight: 600; }
.indice { columns: 2; font-size: 9.4pt; } .indice li { margin: 2px 0; }
"""

SECCIONES = ["Problema, enfoque y arquitectura", "Fuente de datos: descarga, verificación e inventario", "Diagnóstico de calidad de la fuente",
             "Negocio e indicadores", "Modelo dimensional", "Diccionario de datos", "ETL y calidad de datos", "Base de datos",
             "Docker y Kubernetes", "Grafana: tablero operativo y alertas", "Power BI: tablero analítico", "Arquitectura y análisis comparativo",
             "Ética y seguridad", "Evidencias del clúster", "Hallazgos y recomendaciones", "Repositorio y reproducibilidad", "English corner"]


def pagina_html():
    portada = f"""<div class="portada"><div class="barra"></div>
<h1>Taller 6 · BI contenerizado para una microrred híbrida</h1>
<div class="sub">From inverter telemetry to actionable insights: a containerized, Kubernetes-orchestrated BI pipeline for a hybrid microgrid.</div>
<table>
<tr><th>Integrantes</th><td>Andres Asprilla<br>Jorge Andres Grisales</td></tr>
<tr><th>Docente</th><td>Ramiro Grisales Montoya</td></tr>
<tr><th>Curso</th><td>Inteligencia de Negocios · 2026-II<br>Institución Universitaria Pascual Bravo</td></tr>
<tr><th>Enfoque</th><td>SolarBI: perfil de consumo de cargas de cómputo con bitácoras JSON y telemetría eléctrica</td></tr>
<tr><th>Repositorio</th><td>{REPO}</td></tr>
<tr><th>Fecha</th><td>{date.today().strftime('%d de noviembre de %Y') if date.today().month == 11 else date.today().isoformat()}</td></tr>
</table></div>
<h2 style="page-break-before:auto">Contenido</h2><ol class="indice">{''.join(f'<li>{t}</li>' for t in SECCIONES)}</ol>"""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>BI Taller 6</title><style>{CSS}</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js"></script></head>
<body>{portada}{construir()}</body></html>"""


def main():
    tmp = DOCS / "_informe.html"
    tmp.write_text(pagina_html(), encoding="utf-8")
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="msedge", headless=True)
        pag = nav.new_page()
        pag.goto(tmp.as_uri(), wait_until="networkidle")
        n = len(MERMAID)
        if n:
            try:
                pag.evaluate("() => mermaid.initialize({startOnLoad: false, theme: 'neutral', securityLevel: 'loose', flowchart: {htmlLabels: true}})")
                pag.evaluate("() => mermaid.run({querySelector: 'pre.mermaid'})")
                pag.wait_for_timeout(2500)
                print("diagramas dibujados:", pag.evaluate("() => document.querySelectorAll('pre.mermaid svg').length"), "de", n)
            except Exception as e:                                    # sin internet: quedan como texto
                print("aviso: no se pudieron dibujar los diagramas:", e)
        pag.pdf(path=str(SALIDA), format="A4", print_background=True, display_header_footer=True,
                margin={"top": "17mm", "bottom": "17mm", "left": "15mm", "right": "15mm"},
                header_template="<div style='font-size:7px;color:#888;width:100%;padding:0 15mm'>BI Taller 6 · Microrred híbrida · Asprilla y Grisales</div>",
                footer_template="<div style='font-size:7px;color:#888;width:100%;text-align:right;padding:0 15mm'>Página <span class='pageNumber'></span> de <span class='totalPages'></span></div>")
        nav.close()
    tmp.unlink()
    print("PDF:", SALIDA, f"({SALIDA.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
