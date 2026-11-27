#!/usr/bin/env bash
set -euo pipefail

collector=/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
if [[ ! -x "$collector" ]]; then
  case "$(uname -m)" in
    aarch64) arch=arm64 ;;
    x86_64) arch=amd64 ;;
    *) exit 1 ;;
  esac
  temp="$(mktemp -d)"
  trap 'rm -rf -- "$temp"' EXIT
  chmod 700 "$temp"
  repo=https://amazoncloudwatch-agent.s3.amazonaws.com
  package=amazon-cloudwatch-agent.rpm
  for file in "$package" "$package.sig"; do
    curl -fsS --retry 2 --max-time 45 "$repo/amazon_linux/$arch/latest/$file" -o "$temp/$file"
  done
  curl -fsS --retry 2 --max-time 20 "$repo/assets/amazon-cloudwatch-agent.gpg" -o "$temp/signing-key"
  fingerprint="$(gpg --homedir "$temp" --batch --no-autostart --with-colons --show-keys "$temp/signing-key" |
    awk -F: '$1 == "fpr" && !seen++ {print $10}')"
  [[ "$fingerprint" == 937616F3450B7D806CBD9725D58167303B789C72 ]]
  gpg --homedir "$temp" --batch --no-autostart --dearmor -o "$temp/vendor.gpg" "$temp/signing-key"
  if command -v gpgv >/dev/null; then
    gpgv --keyring "$temp/vendor.gpg" "$temp/$package.sig" "$temp/$package"
  else
    gpg --homedir "$temp" --batch --no-autostart --no-default-keyring \
      --keyring "$temp/vendor.gpg" --verify "$temp/$package.sig" "$temp/$package"
  fi
  rpm -U "$temp/$package"
fi

install -d -m 0750 /opt/amaris-log-archive
cat > /opt/amaris-log-archive/sync.py <<'PY'
"""Discover running Academy containers and refresh the CloudWatch file list."""
import json
import pathlib
import re
import subprocess

GROUP = "/amaris/mathematics-academy/staging"
CLUSTER = "amaris-ecs-staging"
CONFIG = pathlib.Path("/opt/amaris-log-archive/amaris-docker.json")
AGENT = "/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl"

container_ids = subprocess.check_output(["docker", "ps", "-q"], text=True).split()
format_string = (
    '{{.Id}}|{{.Name}}|{{.HostConfig.LogConfig.Type}}|{{.LogPath}}|'
    '{{index .Config.Labels "com.amazonaws.ecs.cluster"}}|'
    '{{index .Config.Labels "com.amazonaws.ecs.container-name"}}'
)
entries = []
for container_id in container_ids:
    try:
        result = subprocess.check_output(
            ["docker", "inspect", "--format", format_string, container_id],
            text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        # ECS may remove the container between listing and inspection.
        continue
    identifier, name, driver, log_path, cluster, component = result.rstrip("\n").split("|")
    if cluster == CLUSTER:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", component):
            continue
    elif name.startswith("/amaris-"):
        component = name.removeprefix("/amaris-")
    else:
        continue
    if driver != "json-file" or not log_path or not pathlib.Path(log_path).is_file():
        continue
    entries.append({
        "file_path": log_path,
        "log_group_name": GROUP,
        "log_stream_name": f"{{instance_id}}/{component}/{identifier[:12]}",
    })
if not entries:
    raise SystemExit("No Academy Docker logs found on this host.")

data = json.dumps({"logs": {"force_flush_interval": 5, "logs_collected": {
    "files": {"collect_list": sorted(entries, key=lambda item: item["log_stream_name"])}
}}}, indent=2, sort_keys=True) + "\n"
if CONFIG.exists() and CONFIG.read_text() == data:
    if subprocess.run(["systemctl", "is-active", "--quiet", "amazon-cloudwatch-agent"]).returncode == 0:
        raise SystemExit(0)
candidate = CONFIG.with_suffix(".tmp")
candidate.write_text(data)
candidate.replace(CONFIG)
try:
    subprocess.run([AGENT, "-a", "append-config", "-m", "ec2", "-s", "-c", f"file:{CONFIG}"], check=True)
except subprocess.CalledProcessError:
    CONFIG.unlink(missing_ok=True)
    raise
print(f"Configured CloudWatch collection for {len(entries)} Academy Docker log files.")
PY

cat > /etc/systemd/system/amaris-cloudwatch-log-sync.service <<'UNIT'
[Unit]
Description=Discover Amaris container logs for CloudWatch
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/amaris-log-archive/sync.py
UNIT
cat > /etc/systemd/system/amaris-cloudwatch-log-sync.timer <<'UNIT'
[Unit]
Description=Refresh the Amaris CloudWatch container log sources

[Timer]
OnBootSec=45s
OnUnitActiveSec=45s
Unit=amaris-cloudwatch-log-sync.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now amaris-cloudwatch-log-sync.timer
systemctl start amaris-cloudwatch-log-sync.service || {
  journalctl -u amaris-cloudwatch-log-sync.service --no-pager -n 18
  exit 1
}
systemctl is-active amazon-cloudwatch-agent
