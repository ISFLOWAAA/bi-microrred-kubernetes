# Imagen del simulador: misma base que el ETL (capas compartidas en el equipo y en el clúster),
# pero solo con psycopg: no necesita pandas.
FROM python:3.13.18-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY simulador.py .

RUN useradd --uid 10001 --no-create-home simulador
USER 10001

ENTRYPOINT ["python", "simulador.py"]
