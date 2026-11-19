# Imagen del ETL de la microrred.
# Base: python slim (Debian) con versión fija. No se usa alpine porque pandas y numpy
# publican ruedas listas para glibc; en alpine (musl) habría que compilar o usar ruedas menos probadas.
FROM python:3.13.18-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SQLITE_PATH=/datos/opencem-v1.0.0.sqlite

WORKDIR /app

# Primero las dependencias: esta capa se reutiliza mientras requirements.txt no cambie
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY *.py cargar_gold.sql ./

# Sin privilegios de root. La fuente se monta en /datos (solo lectura); no va dentro de la imagen.
RUN useradd --uid 10001 --no-create-home etl
USER 10001

ENTRYPOINT ["python", "etl.py"]
