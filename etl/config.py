"""Configuración del ETL: todo se lee de variables de entorno (nada sensible en el código).

En Kubernetes las credenciales llegan desde un Secret y los umbrales desde un ConfigMap.
En local se puede usar el archivo .env de la raíz del repositorio (no se sube a GitHub).
"""
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VERSION_ETL = "1.0.0"
TZ_SITIO = "Asia/Shanghai"   # hora local del sitio (UTC+8, sin horario de verano)
OFFSET_LOCAL_S = 8 * 3600


def _cargar_env_local():
    """Lee RAIZ/.env sin sobrescribir variables que ya existan (solo para correr en local)."""
    archivo = RAIZ / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip())


def _num(nombre, defecto):
    return float(os.environ.get(nombre, defecto))


@dataclass(frozen=True)
class Config:
    # Conexión (en el clúster: PGHOST=postgres, el nombre del Service)
    pg_host: str
    pg_puerto: int
    pg_base: str
    pg_usuario: str
    pg_clave: str
    # Fuente
    sqlite: Path
    calcular_sha256: bool
    # Umbrales de limpieza y de eventos (docs/02 y docs/03)
    dt_max_s: float          # tope de Δt entre lecturas (Q3)
    carga_atipica_w: float   # Q6
    soc_bajo_pct: float      # evento SOC_BAJO / alerta O1
    temp_alta_c: float       # evento TEMP_ALTA / alerta O3
    episodio_min: float      # duración mínima de RED_CAIDA y SOC_BAJO
    hueco_min: float         # evento HUECO_DATOS
    capacidad_ah_supuesta: int  # Q11

    @property
    def dsn(self):
        return (f"host={self.pg_host} port={self.pg_puerto} dbname={self.pg_base} "
                f"user={self.pg_usuario} password={self.pg_clave}")


def leer_config() -> Config:
    _cargar_env_local()
    faltan = [v for v in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD") if not os.environ.get(v)]
    if faltan:
        raise SystemExit(f"Faltan variables de entorno: {', '.join(faltan)} (ver .env.example)")
    return Config(
        pg_host=os.environ.get("PGHOST", "localhost"),
        pg_puerto=int(os.environ.get("PGPORT", os.environ.get("PG_PUERTO_HOST", 5432))),
        pg_base=os.environ["POSTGRES_DB"],
        pg_usuario=os.environ["POSTGRES_USER"],
        pg_clave=os.environ["POSTGRES_PASSWORD"],
        sqlite=Path(os.environ.get("SQLITE_PATH", RAIZ / "datos/zenodo/opencem-v1.0.0.sqlite")),
        calcular_sha256=os.environ.get("CALCULAR_SHA256", "true").lower() == "true",
        dt_max_s=_num("DT_MAX_S", 60),
        carga_atipica_w=_num("CARGA_ATIPICA_W", 3000),
        soc_bajo_pct=_num("SOC_BAJO_PCT", 20),
        temp_alta_c=_num("TEMP_ALTA_C", 45),
        episodio_min=_num("EPISODIO_MIN", 5),
        hueco_min=_num("HUECO_MIN", 10),
        capacidad_ah_supuesta=int(_num("CAPACIDAD_AH_SUPUESTA", 200)),
    )
