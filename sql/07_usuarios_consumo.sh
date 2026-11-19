#!/bin/sh
# 07 · Usuarios de consumo de solo lectura (miembros de rol_lectura_bi: SELECT solo en gold,
# sin acceso a bronze). Uno por herramienta, para poder revocar o auditar cada una por separado.
# Es .sh y no .sql porque las contraseñas llegan por variables de entorno (Secret), nunca en el repo.
# PostgreSQL lo ejecuta al iniciar la base vacía, después de 06_seguridad.sql.
set -e
crear() {   # $1 = nombre del rol, $2 = contraseña
  [ -n "$2" ] || return 0
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v rol="$1" -v pw="$2" <<'EOSQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L IN ROLE rol_lectura_bi', :'rol', :'pw')
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'rol') \gexec
EOSQL
}
crear grafana_lector "${GRAFANA_DB_PASSWORD:-}"
crear powerbi_lector "${POWERBI_DB_PASSWORD:-}"
