# Tareas para Jorge

Este archivo es el punto de partida de Jorge en el proyecto. Según el reparto del plan (`docs/PLAN.md`), a Jorge le
tocan **Docker, Kubernetes, simulador y Grafana**. Cada tarea de abajo es una deuda real que quedó anotada en
`docs/09_etica_seguridad.md` o una bonificación del enunciado (§4 K.4). Cada una se entrega como **commits propios de Jorge**.

## 0. Preparación (una sola vez, ~1 hora la primera vez)

1. **Aceptar la invitación** al repositorio: <https://github.com/ISFLOWAAA/bi-microrred-kubernetes/invitations>.
2. **Requisitos del equipo:** Windows con Docker Desktop y Kubernetes activado (Settings → Kubernetes → *Enable*, tipo **kind**),
   Git, Python 3.11+ y 16 GB de RAM.
3. **Clonar y configurar la identidad** (para que los commits salgan a su nombre y cuenten como aporte suyo):
   ```bash
   git clone https://github.com/ISFLOWAAA/bi-microrred-kubernetes.git
   cd bi-microrred-kubernetes
   git config user.name "Jorge Andres Grisales"
   git config user.email "<el correo de su cuenta de GitHub>"
   ```
4. **Contraseñas:** `copy .env.example .env` y poner valores propios (en `.env` nunca se sube a Git). Con una clave nueva para cada línea.
5. **Datos:** el `.sqlite` (4,4 GB) no está en el repositorio. Descargarlo y verificarlo como indica `datos/README.md`
   (Zenodo + checksum SHA-256). Debe quedar en `datos/zenodo/opencem-v1.0.0.sqlite`.
6. **Levantar todo:** `powershell -ExecutionPolicy Bypass -File k8s\levantar.ps1` (~10 min la primera vez: copia la fuente al nodo).
   Al terminar: Grafana en <http://localhost:3001> y PostgreSQL en `localhost:5434`.
7. **Leer, en este orden:** `README.md` → `docs/07_contenedores.md` → `k8s/README.md` → `docs/08_arquitectura_analisis.md` →
   `docs/09_etica_seguridad.md`. Antes de empezar, que pueda explicar con sus palabras **qué hace cada objeto de `k8s/`** y por qué se eligió.
8. **Probar la resiliencia con sus manos:** `kubectl -n taller6 delete pod postgres-0` y comprobar que los datos siguen
   (`docs/evidencias/06_resiliencia.txt` muestra lo esperado).

> Trampas conocidas de Docker Desktop en este proyecto: si `docker pull/build` dice `no such host`, reintentar; `docker compose build`
> falla, usar `docker build -t ...`; el nodo *kind* no ve las imágenes locales (se importan con `levantar.ps1`); si se cambia una
> imagen propia hay que **subir la versión** (`1.0.1` → `1.0.2`), porque el nodo no reimporta la misma etiqueta.

## Reglas de trabajo (para los dos)

- **Una rama por tarea:** `git switch -c jorge/usuarios-minimo-privilegio`, commits pequeños con mensaje en español, y **Pull Request**
  hacia `main` (o al menos `git pull --rebase` antes de cada `git push`).
- **Nunca** subir `.env`, contraseñas ni el `.sqlite`. Antes de cada push: `git status` y revisar que no aparezcan.
- **No regenerar el PDF** (`docs/BI_Taller6_Asprilla_Grisales.pdf`) en cada tarea: es binario y se pisa. Se regenera una sola vez, al final.
- Cada tarea termina con **evidencia** (una salida real de `kubectl` o `psql` en `docs/evidencias/`) y con la **fila de riesgo actualizada**
  en `docs/09_etica_seguridad.md`.
- **Nada a mano en la sustentación:** si algo se crea con `kubectl create` o desde la interfaz de Grafana, ese ítem no se califica.
  Todo cambio queda en un archivo versionado.

## Tareas

### T1 · Usuarios de mínimo privilegio para el ETL y el simulador  `(prioridad alta)`

**Problema:** hoy el Job del ETL y el CronJob del simulador usan el usuario **administrador** (`POSTGRES_USER` del Secret).
Los roles `rol_etl` y `rol_simulador` existen (`sql/06_seguridad.sql`) pero nadie inicia sesión con ellos.

**Qué hacer**
1. En `sql/07_usuarios_consumo.sh` crear dos usuarios con login: `etl_cargador` (miembro de `rol_etl`) y `simulador_escritor` (miembro de `rol_simulador`),
   con contraseñas que lleguen por variables de entorno (`ETL_DB_PASSWORD`, `SIM_DB_PASSWORD`), igual que `grafana_lector`.
2. Agregar esas variables a `.env.example`.
3. Crear **un Secret por carga de trabajo** (en `levantar.ps1`) con las claves `POSTGRES_USER` y `POSTGRES_PASSWORD` de cada uno, y hacer que
   `k8s/03-etl-job.yaml` y `k8s/04-simulador-cronjob.yaml` usen su propio Secret en lugar de `pg-credenciales`.

**Cuidado (aquí está lo que se aprende):**
- Los scripts de `sql/` solo corren con la base **vacía**: para probar, `borrar.ps1` y luego `levantar.ps1`.
- `rol_etl` no es dueño de las tablas: `ANALYZE` solo funciona sobre tablas propias en PostgreSQL 16, y sin él el paso de tareas del ETL
  vuelve a tardar ~7 min en vez de 2 s (`docs/06_etl_calidad.md`, §8). Decidir y justificar cómo se resuelve (¿`ALTER ... OWNER`? ¿el ETL como dueño?).
- El simulador usa la función `gold.inversor_sk_vigente()`: necesita `EXECUTE` y `SELECT` sobre las dimensiones.

**Listo cuando:** el Job termina `Complete`; `silver.etl_ejecucion` muestra la ejecución `exitosa`; `kubectl -n taller6 describe job etl-carga-historica`
ya no referencia el Secret del administrador; y se puede explicar qué pasa si se intenta `DROP TABLE` con `etl_cargador`.

### T2 · Actualización sin corte y reversión (bonificación)

El simulador es un `CronJob`, así que una actualización de imagen solo afecta a la siguiente ejecución. Para demostrar un *rolling update* de verdad:

1. Escribir `k8s/extra/simulador-deployment.yaml`: el mismo simulador como `Deployment` (con `MODO: bucle`) y `strategy: RollingUpdate`.
2. Construir `taller6/simulador:1.0.2` con un cambio visible (por ejemplo una línea distinta en el log) e importarla al nodo
   (`docker save ... | docker exec -i desktop-control-plane ctr -n k8s.io images import -`).
3. Actualizar con `kubectl -n taller6 set image deployment/simulador-vivo simulador=taller6/simulador:1.0.2`, seguirlo con
   `kubectl rollout status` y luego revertir con `kubectl rollout undo` y revisar `kubectl rollout history`.
4. Guardar la salida en `docs/evidencias/07_rolling_update.txt` y explicar en 3 líneas por qué el simulador de producción sigue siendo un CronJob.

### T3 · Kustomize con ambientes `dev` y `demo` (bonificación)

Estructura sugerida: `k8s/base/` (los manifiestos actuales) y `k8s/overlays/dev/` y `k8s/overlays/demo/` con las diferencias
(por ejemplo `ESCENARIO`, `MAX_MINUTOS`, `requests/limits` más bajos en `dev`). Cambiar `levantar.ps1` para usar `kubectl apply -k`.

**Cuidado:** Kustomize no deja leer archivos fuera de su carpeta (`sql/`, `grafana/`), así que los ConfigMap que hoy crea `levantar.ps1`
con `--from-file` hay que dejarlos en el script o resolverlos con `configMapGenerator` y una copia o enlace. Documentar la decisión en `k8s/README.md`.

### T4 · Canal de notificación para las alertas de Grafana

Hoy las alertas solo se ven en el tablero (`grafana/README.md` lo dice). Que lleguen a un destino:
1. Crear `grafana/provisioning/alerting/contactpoints.yaml` con un *contact point* tipo **webhook** y una política de notificación que lo use.
2. Para probarlo sin cuentas externas, desplegar un receptor mínimo en el clúster (un `Deployment` + `Service` con una imagen de eco HTTP **con versión fija**)
   y ver llegar el mensaje con `kubectl logs`.
3. Montar el nuevo archivo en el ConfigMap de alertas (`levantar.ps1` ya empaqueta `grafana/provisioning/alerting/`) y disparar la alerta con
   `ESCENARIO=red_caida` (`simulador/README.md`).

**Listo cuando:** al cambiar el escenario, el log del receptor muestra la alerta de **Red caída**, y todo quedó en archivos (nada configurado desde la interfaz).

### T5 · Cerrar la exposición de puertos

Grafana (3001) y PostgreSQL (5434) escuchan en `0.0.0.0` (`docs/09_etica_seguridad.md`, §2.1). Crear una regla del Firewall de Windows que bloquee
el acceso desde otras máquinas (PowerShell como administrador, `New-NetFirewallRule`, sentido de entrada, puertos `3001,5434`), comprobar que
`localhost` **sigue funcionando** (Grafana, DBeaver y Power BI) y documentar el comando y su verificación. Actualizar la fila de riesgo.

### T6 · Ensayo de las preguntas en vivo (juntos, antes de la sustentación)

El enunciado dice que el docente puede pedir cualquiera de estas cosas **en vivo**. Cada uno debe poder hacerlas sin ayuda:

| # | Pedido del docente | Dónde se hace |
|---|---|---|
| 1 | Borrar el pod de PostgreSQL y mostrar que los datos siguen | `kubectl delete pod` |
| 2 | Borrar el pod de Grafana y mostrar que vuelve con su tablero | `kubectl delete pod -l app=grafana` |
| 3 | Cambiar un umbral **sin reconstruir la imagen** | ConfigMap (`SOC_BAJO_PCT`, `ESCENARIO`) o `alertas.yaml` + `levantar.ps1` |
| 4 | Agregar un panel a Grafana | Editar `grafana/tableros/microrred.json` (no la interfaz) y recargar el ConfigMap |
| 5 | Escribir una medida DAX nueva | `powerbi/generar_proyecto.py` o directamente en Power BI |
| 6 | Modificar una consulta | `sql/consultas/` o las vistas de `sql/05_gold_vistas.sql` |
| 7 | Levantar todo desde cero con un comando | `borrar.ps1` y `levantar.ps1` |

## Cómo se ve un buen aporte

- Commits pequeños, con mensaje claro (`Crear usuarios de mínimo privilegio para el ETL y el simulador`), de varios días y no uno solo al final.
- Cada tarea con su rama y su PR, con la evidencia y la documentación actualizada.
- Que Jorge sepa explicar cada línea que subió: el docente lo puede preguntar a cualquiera de los dos.
