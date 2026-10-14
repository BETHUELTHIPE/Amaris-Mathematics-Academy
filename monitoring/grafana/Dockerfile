FROM grafana/grafana:12.2.0
COPY monitoring/grafana/provisioning/ /etc/grafana/provisioning/
# A Render persistent disk is mounted over /var/lib/grafana. Keep dashboard
# source files outside the disk so they remain present after restart.
COPY monitoring/grafana/dashboards/ /etc/grafana/dashboards/
EXPOSE 10000
