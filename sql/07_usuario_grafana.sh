#!/bin/sh
# 07 · Usuario de solo lectura para Grafana (miembro de rol_lectura_bi: solo SELECT en gold).
# Es .sh y no .sql porque la contraseña llega por variable de entorno (Secret), nunca en el repo.
# PostgreSQL lo ejecuta al iniciar la base vacía, después de 06_seguridad.sql.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="${GRAFANA_DB_PASSWORD:-}" <<'EOSQL'
SELECT format('CREATE ROLE grafana_lector LOGIN PASSWORD %L IN ROLE rol_lectura_bi', :'pw')
 WHERE :'pw' <> '' AND NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_lector') \gexec
EOSQL
