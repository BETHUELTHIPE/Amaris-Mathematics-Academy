FROM apache/airflow:3.3.2-python3.12

# Airflow does not emit StatsD metrics unless the optional extra is installed.
# Keep core/extras pinned to the parent image release.
USER airflow
RUN pip install --no-cache-dir "apache-airflow[statsd]==3.3.2"
