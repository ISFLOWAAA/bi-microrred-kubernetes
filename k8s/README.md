# k8s/

Despliegue en el Kubernetes de Docker Desktop (modo *kind*). Todo vive en el namespace `taller6`.

```powershell
powershell -ExecutionPolicy Bypass -File k8s\levantar.ps1    # un comando para levantar (~10 min la 1.ª vez)
powershell -ExecutionPolicy Bypass -File k8s\borrar.ps1      # un comando para borrar
```

Requisitos: Docker Desktop con Kubernetes activado, `.env` en la raíz y la SQLite en `datos/zenodo/`.

## Qué hace `levantar.ps1`

1. Construye las imágenes propias si no existen.
2. Las importa al nodo: en modo *kind* el nodo es un contenedor y **no ve las imágenes locales de Docker**.
3. Copia la SQLite (4,4 GB) dentro del nodo, solo la primera vez: el nodo **no monta el disco de Windows**.
4. Crea el namespace, el Secret (desde `.env`) y los ConfigMaps (`sql/` y la configuración).
5. Aplica PostgreSQL, el Job del ETL y el CronJob del simulador.
6. Espera a que el ETL termine y muestra el resultado.

## Objetos (tabla K.3)

| Necesidad | Objeto | Archivo |
|---|---|---|
| Aislar el proyecto | `Namespace` `taller6` | `00-namespace.yaml` |
| Credenciales fuera del código | `Secret` `pg-credenciales` (creado desde `.env`, nunca en el repo) | `levantar.ps1` |
| Configuración separada | `ConfigMap` `config-microrred` (host, umbrales, escenario) y `sql-init` (DDL) | `01-config.yaml`, `levantar.ps1` |
| BD que no pierde datos | `StatefulSet` + `PersistentVolumeClaim` de 5 Gi | `02-postgres.yaml` |
| Encontrar PostgreSQL por nombre | `Service` headless `postgres` → `PGHOST=postgres` | `02-postgres.yaml` |
| Acceso desde el anfitrión | `Service` `LoadBalancer` → `localhost:5434` | `02-postgres.yaml` |
| Carga histórica una vez | `Job` `etl-carga-historica` (espera a la base con un *initContainer*) | `03-etl-job.yaml` |
| Datos nuevos periódicos | `CronJob` `simulador` cada minuto | `04-simulador-cronjob.yaml` |
| Saber si está sano | `readinessProbe` y `livenessProbe` con `pg_isready` | `02-postgres.yaml` |
| No agotar el equipo | `resources.requests` / `limits` en todos los contenedores | todos |

**Por qué `LoadBalancer` y no `NodePort`:** en Docker Desktop con *kind* el NodePort queda dentro del
contenedor del nodo y no llega a Windows (se probó: el puerto no responde); Docker Desktop sí publica los
`LoadBalancer` en `localhost`.

## Comandos útiles

```powershell
kubectl -n taller6 get pods,svc,pvc,jobs,cronjobs
kubectl -n taller6 logs job/etl-carga-historica             # reglas de calidad y conciliación
kubectl -n taller6 delete pod postgres-0                     # prueba de recuperación: vuelve solo y con sus datos
kubectl -n taller6 patch configmap config-microrred -p '{\"data\":{\"ESCENARIO\":\"red_caida\"}}'   # probar alertas
```
