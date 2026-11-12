# Disposable HTTP acceptance image only; the release uses backend/Dockerfile.
FROM python:3.13.15-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
CMD ["python", "tests/site_gateway/start_django.py"]
