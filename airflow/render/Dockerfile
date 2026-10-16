FROM apache/airflow:3.3.2-python3.12

USER airflow
RUN pip install --no-cache-dir \
    "apache-airflow[statsd]==3.3.2" "apache-airflow-providers-fab==3.9.0" \
    --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt

# Render has no Compose bind mounts: every service receives the same DAG release.
COPY --chown=airflow:root dags /opt/airflow/dags
COPY --chown=airflow:root render/start.py /opt/airflow/render/start.py
ENV AIRFLOW__CORE__DAGS_FOLDER=/opt/airflow/dags
# Keep the official image entrypoint (signal handling/user setup).
CMD ["python", "/opt/airflow/render/start.py", "api"]
