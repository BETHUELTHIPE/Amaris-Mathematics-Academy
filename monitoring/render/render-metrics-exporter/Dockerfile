FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY monitoring/render/render-metrics-exporter/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY monitoring/render/render-metrics-exporter/exporter.py /app/exporter.py

EXPOSE 10000
CMD ["python", "/app/exporter.py"]
