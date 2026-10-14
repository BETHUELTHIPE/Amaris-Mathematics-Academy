FROM prom/prometheus:v3.15.0
USER root
COPY monitoring/render/prometheus/prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl
COPY monitoring/render/prometheus/alerts.yml /etc/prometheus/alerts.yml
COPY monitoring/render/prometheus/start.sh /etc/prometheus/start.sh
RUN chmod 755 /etc/prometheus/start.sh
EXPOSE 10000
ENTRYPOINT ["/bin/sh", "/etc/prometheus/start.sh"]
