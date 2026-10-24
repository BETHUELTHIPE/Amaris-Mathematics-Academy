FROM grafana/grafana:13.2.4
COPY monitoring/render/grafana/provisioning/ /etc/grafana/provisioning/
COPY monitoring/render/grafana/dashboards/ /etc/grafana/dashboards/
COPY monitoring/render/grafana/datasource-templates/ /etc/amaris/datasource-templates/
COPY --chmod=755 monitoring/render/grafana/entrypoint.sh /etc/amaris/entrypoint.sh
ENTRYPOINT ["/etc/amaris/entrypoint.sh"]
EXPOSE 10000
