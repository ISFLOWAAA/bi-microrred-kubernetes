# datos/

Aquí van los archivos descargados de Zenodo. **Esta carpeta no se sube a GitHub** (solo este README).

Origen: https://zenodo.org/records/21436223 (OpenCEM v1.0.0, DOI 10.5281/zenodo.21436223, licencia CC BY 4.0)

## 1. Descarga

Se descargan solo los archivos necesarios (~312 MB) en `datos/zenodo/`:

| Archivo | Tamaño | Uso |
|---|---|---|
| `opencem-v1.0.0.sqlite.zst` | 302,1 MB | Fuente de datos del taller |
| `opencem-v1.0.0-support.zip` | 10,0 MB | Documentación, diccionario de columnas, código de los autores |
| `opencem-v1.0.0-SHA256SUMS.txt` | 849 B | Verificación de integridad |
| `README.md` y `LICENSE-DATA.txt` | < 5 kB | Descripción y licencia |

Las imágenes de cielo (`opencem-v1.0.0-sky-*.tar.zst`) **no** se descargan: están fuera del alcance.

```bash
mkdir -p datos/zenodo && cd datos/zenodo
BASE="https://zenodo.org/records/21436223/files"
for f in opencem-v1.0.0-SHA256SUMS.txt README.md LICENSE-DATA.txt \
         opencem-v1.0.0-support.zip opencem-v1.0.0.sqlite.zst; do
  curl -fL --retry 5 -C - -o "$f" "$BASE/$f?download=1"
done
```

> `-C -` permite reanudar la descarga si se corta (nos pasó con el `.sqlite.zst`).

## 2. Verificación de integridad (checksum SHA-256)

```bash
cd datos/zenodo
grep -E " (README.md|LICENSE-DATA.txt|opencem-v1.0.0-support.zip|opencem-v1.0.0.sqlite.zst)$" \
  opencem-v1.0.0-SHA256SUMS.txt | sha256sum -c -
```

Evidencia (2026-11-19):

```
LICENSE-DATA.txt: OK
README.md: OK
opencem-v1.0.0-support.zip: OK
opencem-v1.0.0.sqlite.zst: OK
```

| Archivo | SHA-256 esperado |
|---|---|
| `opencem-v1.0.0.sqlite.zst` | `8e38f98209029367a3775799ee9a7c0757cc7e8f2742e4df4eccc45dd4b27517` |
| `opencem-v1.0.0-support.zip` | `5debdbebb82ed784e1c11ac70c81fe876400a049a001a8dc2230446e2f460439` |

## 3. Descompresión

**Herramienta:** módulo `compression.zstd` de la librería estándar de **Python 3.14** (no requiere instalar
`zstd`). Alternativa equivalente con la herramienta oficial: `zstd -d opencem-v1.0.0.sqlite.zst`.

```bash
cd datos/zenodo
python -c "
import shutil
from compression import zstd
with zstd.open('opencem-v1.0.0.sqlite.zst','rb') as src, open('opencem-v1.0.0.sqlite','wb') as dst:
    shutil.copyfileobj(src, dst, 16*1024*1024)
"
python -c "import zipfile; zipfile.ZipFile('opencem-v1.0.0-support.zip').extractall('.')"
```

Resultado: `opencem-v1.0.0.sqlite` de **4,44 GB** (4 439 408 640 bytes), descomprimido en ~10 s,
y la carpeta `opencem-v1.0.0/` con la documentación de soporte.

## 4. Inventario

```bash
python etl/inventario_fuente.py
```

Genera [`docs/01_inventario_fuente.md`](../docs/01_inventario_fuente.md): tablas, columnas, filas y periodo de cada una.

## Estructura final

```
datos/
├── README.md                      ← este archivo (único que se versiona)
└── zenodo/
    ├── opencem-v1.0.0.sqlite      ← capa Bronze (solo lectura, nunca se modifica)
    ├── opencem-v1.0.0.sqlite.zst
    ├── opencem-v1.0.0-support.zip
    ├── opencem-v1.0.0/            ← soporte descomprimido (documentation/, code/, validation/)
    ├── opencem-v1.0.0-SHA256SUMS.txt
    ├── README.md
    └── LICENSE-DATA.txt
```

El archivo `.sqlite` es la capa **Bronze**: el ETL lo abre en modo solo lectura (`mode=ro`).
