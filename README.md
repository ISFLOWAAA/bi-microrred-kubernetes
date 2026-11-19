# Taller 6 · BI contenerizado para una microrred híbrida

> *From inverter telemetry to actionable insights: a containerized, Kubernetes-orchestrated BI pipeline for a hybrid microgrid.*

Institución Universitaria Pascual Bravo · Inteligencia de Negocios · 2026-II
Docente: Ramiro Grisales Montoya
Integrantes: Andres Asprilla · Jorge Andres Grisales

**Enfoque de profundización: SolarBI** — perfil de consumo de cargas de cómputo con bitácoras JSON y telemetría eléctrica.

## ¿Qué es?

Una solución de Inteligencia de Negocios que toma la telemetría real de una microrred
(solar + batería + red) y la convierte en indicadores para tomar decisiones.

> ¿Cuánta energía consume cada tipo de tarea de cómputo, de dónde sale (sol, batería o red) y cuánto cuesta?

## ¿Cómo funciona?

```
datos (.sqlite)  →  etl  →  PostgreSQL (Bronze / Silver / Gold)  →  Grafana  (monitoreo y alertas)
                               ↑                                  →  Power BI (análisis)
                           simulador
            (todo corre en Kubernetes local)
```

## ¿Dónde está cada cosa?

| Carpeta | Contenido |
|---|---|
| `docs/` | Diseño, indicadores, diccionario, arquitectura, ética y seguridad, hallazgos, evidencias del clúster, capturas e informe PDF |
| `datos/` | Datos descargados de Zenodo (**no se suben a GitHub**) |
| `sql/` | Creación de tablas y consultas de negocio |
| `etl/` | Proceso que limpia y carga los datos + Dockerfile |
| `simulador/` | Genera datos nuevos para Grafana + Dockerfile |
| `grafana/` | Tablero y configuración automática |
| `powerbi/` | Proyecto de Power BI |
| `k8s/` | Manifiestos de Kubernetes |

## Requisitos del equipo

- Windows con Docker Desktop y Kubernetes activado
- Git, Python 3.11 o superior, DBeaver, Power BI Desktop
- 16 GB de RAM recomendados

## Cómo levantarlo

**En Kubernetes (Docker Desktop)** — un comando para levantar y otro para borrar:

```powershell
powershell -ExecutionPolicy Bypass -File k8s\levantar.ps1   # PostgreSQL → Job ETL → CronJob simulador
powershell -ExecutionPolicy Bypass -File k8s\borrar.ps1
```

PostgreSQL del clúster: `localhost:5434`. Detalles en [`k8s/README.md`](k8s/README.md).

Grafana: <http://localhost:3001>. Power BI: abrir [`powerbi/Microrred.pbip`](powerbi/README.md) (usuario `powerbi_lector`).

**Prueba local con Docker Compose:**

```bash
cp .env.example .env                        # poner una contraseña real
docker build -t taller6/etl:1.0.0 etl
docker build -t taller6/simulador:1.0.1 simulador
docker compose up -d                        # PostgreSQL → ETL (una vez, ~10 min) → simulador
```

Con Compose, PostgreSQL queda en `localhost:5433`. Detalles en
[`docs/07_contenedores.md`](docs/07_contenedores.md).

## Informe

`docs/BI_Taller6_Asprilla_Grisales.pdf` reúne todos los componentes con capturas y evidencias del clúster.
Se regenera con `python docs/generar_informe.py` (necesita `pip install markdown playwright` y Microsoft Edge).

## Datos y cita

Los datos se descargan de Zenodo: https://zenodo.org/records/21436223 (licencia CC BY 4.0).
Las instrucciones de descarga y verificación están en [`datos/README.md`](datos/README.md).

> Bartels, T. S., Wu, R., Lu, X., Chen, Y., Lu, Y., Xia, F., Yang, H., Chen, Y., & Li, T. (2026).
> *OpenCEM: Multimodal photovoltaic and battery microgrid dataset with context records and sky imagery*
> (Version 1.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.21436223
