# Borra la solución completa del clúster (incluido el volumen de PostgreSQL).
# Uso:  powershell -ExecutionPolicy Bypass -File k8s\borrar.ps1
# La copia de la SQLite dentro del nodo se conserva para que el próximo arranque sea rápido;
# para quitarla también:  -BorrarFuente
param([switch]$BorrarFuente)
kubectl delete namespace taller6 --ignore-not-found --wait=true
if ($BorrarFuente) { docker exec desktop-control-plane rm -rf /datos-taller6 }
Write-Host "Solución eliminada del clúster." -ForegroundColor Green
