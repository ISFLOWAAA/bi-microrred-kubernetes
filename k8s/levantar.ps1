# Levanta la solución completa en el Kubernetes de Docker Desktop (modo kind).
# Uso (desde la raíz del repo):  powershell -ExecutionPolicy Bypass -File k8s\levantar.ps1
# Es idempotente: se puede ejecutar varias veces.
$ErrorActionPreference = "Stop"
$raiz  = Split-Path -Parent $PSScriptRoot
$nodo  = "desktop-control-plane"
$ns    = "taller6"
$imagenes = @("postgres:16.15-alpine", "taller6/etl:1.0.0", "taller6/simulador:1.0.0")

function Paso($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }

if (-not (Test-Path "$raiz\.env")) { throw "Falta .env (copiar .env.example y poner la contraseña)" }
if ((kubectl config current-context) -ne "docker-desktop") { throw "El contexto de kubectl no es docker-desktop" }

Paso "1/6 Imágenes propias"
foreach ($d in @("etl", "simulador")) {
    docker image inspect "taller6/${d}:1.0.0" *> $null
    if ($LASTEXITCODE -ne 0) { docker build -t "taller6/${d}:1.0.0" "$raiz\$d"; if ($LASTEXITCODE -ne 0) { throw "Falló el build de $d" } }
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

Paso "5/6 PostgreSQL, ETL y simulador"
kubectl apply -f "$raiz\k8s\02-postgres.yaml" -f "$raiz\k8s\03-etl-job.yaml" -f "$raiz\k8s\04-simulador-cronjob.yaml"
kubectl -n $ns rollout status statefulset/postgres --timeout=300s

Paso "6/6 Esperando la carga histórica (~10 min la primera vez)"
kubectl -n $ns wait --for=condition=complete job/etl-carga-historica --timeout=3600s
kubectl -n $ns logs job/etl-carga-historica --tail=4
kubectl -n $ns get pods,svc,pvc,cronjob
Write-Host "`nListo. PostgreSQL desde el equipo: localhost:5434 (usuario y clave del .env)" -ForegroundColor Green
