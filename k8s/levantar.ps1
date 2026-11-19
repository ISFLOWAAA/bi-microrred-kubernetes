# Levanta la solución completa en el Kubernetes de Docker Desktop (modo kind).
# Uso (desde la raíz del repo):  powershell -ExecutionPolicy Bypass -File k8s\levantar.ps1
# Es idempotente: se puede ejecutar varias veces.
$ErrorActionPreference = "Stop"
$raiz  = Split-Path -Parent $PSScriptRoot
$nodo  = "desktop-control-plane"
$ns    = "taller6"
$imagenes = @("postgres:16.15-alpine", "grafana/grafana:11.2.0", "taller6/etl:1.0.0", "taller6/simulador:1.0.1")

function Paso($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }

if (-not (Test-Path "$raiz\.env")) { throw "Falta .env (copiar .env.example y poner la contraseña)" }
if ((kubectl config current-context) -ne "docker-desktop") { throw "El contexto de kubectl no es docker-desktop" }

Paso "1/6 Imágenes propias"
foreach ($img in ($imagenes | Where-Object { $_ -like "taller6/*" })) {
    $d = ($img -split "[/:]")[1]                       # taller6/etl:1.0.0 → etl
    docker image inspect $img *> $null
    if ($LASTEXITCODE -ne 0) { docker build -t $img "$raiz\$d"; if ($LASTEXITCODE -ne 0) { throw "Falló el build de $d" } }
}

Paso "2/6 Imágenes dentro del nodo (kind no ve las imágenes locales de Docker)"
$enNodo = docker exec $nodo crictl images
foreach ($img in $imagenes) {
    $repo, $tag = $img -split ":"
    if (-not ($enNodo | Select-String -SimpleMatch "$repo " | Select-String -SimpleMatch " $tag ")) {
        Write-Host "   importando $img"
        cmd /c "docker save $img | docker exec -i $nodo ctr -n k8s.io images import -" | Out-Null
    }
}

Paso "3/6 Fuente SQLite dentro del nodo (solo la primera vez, ~3 min)"
docker exec $nodo test -f /datos-taller6/opencem-v1.0.0.sqlite
if ($LASTEXITCODE -ne 0) {
    docker exec $nodo mkdir -p /datos-taller6
    docker cp "$raiz\datos\zenodo\opencem-v1.0.0.sqlite" "${nodo}:/datos-taller6/opencem-v1.0.0.sqlite"
}

Paso "4/6 Namespace, Secret (desde .env), ConfigMaps"
kubectl apply -f "$raiz\k8s\00-namespace.yaml"
# cmd /c: la tubería de PowerShell 5.1 re-codifica el texto y rompe las tildes del DDL ('Compilación' → 'Compilaci?n')
cmd /c "kubectl -n $ns create secret generic pg-credenciales --from-env-file=`"$raiz\.env`" --dry-run=client -o yaml | kubectl apply -f -"
cmd /c "kubectl -n $ns create configmap sql-init --from-file=`"$raiz\sql`" --dry-run=client -o yaml | kubectl apply -f -"
kubectl apply -f "$raiz\k8s\01-config.yaml"
$g = "$raiz\grafana"
foreach ($cm in @(@("grafana-datasources", "$g\provisioning\datasources"), @("grafana-proveedor", "$g\provisioning\dashboards"),
                  @("grafana-alertas", "$g\provisioning\alerting"), @("grafana-tableros", "$g\tableros"))) {
    cmd /c "kubectl -n $ns create configmap $($cm[0]) --from-file=`"$($cm[1])`" --dry-run=client -o yaml | kubectl apply -f -"
}

Paso "5/6 PostgreSQL, ETL, simulador y Grafana"
kubectl apply -f "$raiz\k8s\02-postgres.yaml" -f "$raiz\k8s\03-etl-job.yaml" -f "$raiz\k8s\04-simulador-cronjob.yaml" -f "$raiz\k8s\05-grafana.yaml"
kubectl -n $ns rollout status statefulset/postgres --timeout=300s

Paso "6/6 Esperando la carga histórica (~10 min la primera vez)"
kubectl -n $ns wait --for=condition=complete job/etl-carga-historica --timeout=3600s
kubectl -n $ns logs job/etl-carga-historica --tail=4
kubectl -n $ns get pods,svc,pvc,cronjob
kubectl -n $ns rollout restart deployment/grafana | Out-Null   # recoge cambios del tablero o de las alertas
kubectl -n $ns rollout status deployment/grafana --timeout=180s
Write-Host "`nListo." -ForegroundColor Green
Write-Host "  Grafana:    http://localhost:3001  (admin / GRAFANA_ADMIN_PASSWORD del .env)"
Write-Host "  PostgreSQL: localhost:5434          (usuario y clave del .env)"
