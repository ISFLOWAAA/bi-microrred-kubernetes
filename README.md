# Taller 6 · BI contenerizado para una microrred híbrida

> *From inverter telemetry to actionable insights: a containerized, Kubernetes-orchestrated BI pipeline for a hybrid microgrid.*

Institución Universitaria Pascual Bravo · Inteligencia de Negocios · 2026-II
Docente: Ramiro Grisales Montoya
Integrantes: Andres Asprilla · Jorge Andres Grisales

## ¿Qué es?

Una solución de Inteligencia de Negocios que toma la telemetría real de una microrred
(solar + batería + red) y la convierte en indicadores para tomar decisiones.

**Línea de profundización:** perfil de consumo de cargas de cómputo, cruzando las
bitácoras JSON con la telemetría eléctrica.

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
| `docs/` | Diseño, indicadores, diccionario de datos, diagramas e informe |
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

_Pendiente: se completará cuando la solución esté construida._

## Datos y cita

Los datos se descargan de Zenodo: https://zenodo.org/records/21436223 (licencia CC BY 4.0).
Las instrucciones de descarga y verificación están en [`datos/README.md`](datos/README.md).

> Bartels, T. S., Wu, R., Lu, X., Chen, Y., Lu, Y., Xia, F., Yang, H., Chen, Y., & Li, T. (2026).
> *OpenCEM: Multimodal photovoltaic and battery microgrid dataset with context records and sky imagery*
> (Version 1.0.0) [Dataset]. Zenodo. https://doi.org/10.5281/zenodo.21436223
