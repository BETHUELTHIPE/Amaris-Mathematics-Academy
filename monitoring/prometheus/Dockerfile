FROM prom/prometheus:v3.5.0
USER root
COPY monitoring/prometheus/prometheus.yml.tmpl /etc/prometheus/prometheus.yml.tmpl
COPY monitoring/prometheus/start.sh /etc/prometheus/start.sh
RUN chmod 755 /etc/prometheus/start.sh
EXPOSE 10000
ENTRYPOINT ["/bin/sh", "/etc/prometheus/start.sh"]
