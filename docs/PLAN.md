# Plan de trabajo · Taller 6

Idea general: **datos → ETL → PostgreSQL → Grafana + Power BI**, todo corriendo en Kubernetes local.
Cada fase deja algo funcionando y un commit en GitHub.

| # | Fase | Qué hacemos | Dónde queda | Enunciado |
|---|---|---|---|---|
| 0 | Preparación | Estructura de carpetas, `.gitignore`, README, repo en GitHub, integrantes | raíz | §5 |
| 1 | Datos | Descargar de Zenodo, verificar checksum, descomprimir, inventariar tablas | `datos/`, `docs/` | §9 |
| 2 | Negocio | Usuarios, preguntas de negocio, diagnóstico de calidad, catálogo de indicadores | `docs/` | §4 A, B |
| 3 | Modelo | Esquema estrella, grano, dimensiones, matriz de bus, diccionario de datos | `docs/` | §4 C, D |
| 4 | Base de datos | Tablas Bronze/Silver/Gold, índices, consultas de negocio y JSON | `sql/` | §4 F |
| 5 | ETL | Script en Python: extrae, limpia (con conteos), carga, concilia; idempotente | `etl/` | §4 E |
| 6 | Docker | Dockerfile del ETL y del simulador + `docker-compose.yml` para probar local | `etl/`, `simulador/`, raíz | §4 K.1 |
| 7 | Kubernetes | Manifiestos YAML, un comando para levantar y otro para borrar | `k8s/` | §4 K.2–K.4 |
| 8 | Grafana | Tablero, variable por inversor, 2 alertas, simulador en el clúster | `grafana/`, `simulador/` | §4 H |
| 9 | Power BI | 3 páginas, tabla de fechas, medidas DAX, balance energético, what-if | `powerbi/` | §4 G |
| 10 | Cierre | Diagrama de arquitectura, Power BI vs Grafana, ética (Ley 1581), seguridad, informe PDF | `docs/` | §4 I, J, §6 |
| 11 | Sustentación | Ensayo en vivo: levantar desde cero, borrar pods, historia con datos | — | §7 |

## Decisiones iniciales (se justifican en el informe)

| Tema | Elección | Por qué |
|---|---|---|
| Clúster | Kubernetes de Docker Desktop | Ya está instalado; las imágenes locales se ven sin registro |
| ETL | Python (pandas + psycopg) | Lee SQLite y JSON sin herramientas extra; corre fácil en un contenedor |
| PostgreSQL | `postgres:16` con versión fija | Imagen oficial, nada de `latest` |
| Grafana | `grafana/grafana` con versión fija | Imagen oficial, con provisioning por archivos |
| Power BI | Formato PBIP | Son archivos de texto: se pueden versionar en Git |
| Credenciales | Secret de Kubernetes + `.env.example` en el repo | La contraseña real nunca se sube |

## Objetos de Kubernetes previstos (tabla K.3)

| Necesidad | Objeto |
|---|---|
| Aislar el proyecto | `Namespace` |
| BD que no pierde datos | `StatefulSet` + `PersistentVolumeClaim` |
| Grafana siempre disponible | `Deployment` + `ConfigMap` de provisioning |
| Credenciales fuera del código | `Secret` |
| Configuración separada | `ConfigMap` |
| Encontrar PostgreSQL por nombre | `Service` |
| Carga histórica una vez | `Job` |
| Datos nuevos periódicos | `CronJob` |
| Saber si está sano | `livenessProbe` / `readinessProbe` |
| No agotar el equipo | `resources.requests` / `limits` |
| Acceso desde el anfitrión | `Service` tipo `NodePort` |

## Reparto sugerido (ambos deben entender todo)

- **Integrante 1:** datos, modelo, SQL, ETL, Power BI.
- **Integrante 2:** Docker, Kubernetes, simulador, Grafana.
- **Juntos:** indicadores, informe y ensayo de la sustentación.
- Cada uno hace commits de su parte para que se vean los aportes.

## Avance

- [x] Fase 0 · Estructura del repositorio
- [x] Fase 0 · Integrantes en el README y repo en GitHub
- [x] Fase 1 · Datos descargados, verificados e inventariados
- [x] Fase 2 · Negocio e indicadores
- [x] Fase 3 · Modelo dimensional y diccionario
- [ ] Fase 4 · Base de datos
- [ ] Fase 5 · ETL
- [ ] Fase 6 · Docker
- [ ] Fase 7 · Kubernetes
- [ ] Fase 8 · Grafana y simulador
- [ ] Fase 9 · Power BI
- [ ] Fase 10 · Arquitectura, ética e informe
- [ ] Fase 11 · Sustentación
