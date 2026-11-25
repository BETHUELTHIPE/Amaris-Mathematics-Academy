#!/usr/bin/env bash
set -euo pipefail
printf 'Host memory and CPU credit relevant load:\n'
free -m
uptime
printf 'Containers persistently running:\n'
docker ps --format '{{.Names}} {{.Status}}'
printf 'ECS task ports and readiness status:\n'
for family in amaris-ecs-staging-private-web amaris-ecs-staging-alb-web; do
  container="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter label=com.amazonaws.ecs.container-name=backend)"
  if [[ ! "$container" =~ ^[a-f0-9]{12,64}$ ]]; then continue; fi
  pid="$(docker inspect --format '{{.State.Pid}}' "$container")"
  printf '%s\n' "$family"
  probe='import http.client,sys; c=http.client.HTTPConnection("127.0.0.1",8000,timeout=8); c.request("GET",sys.argv[1],headers={"Host":"16.171.164.5","X-Forwarded-Proto":"https"}); r=c.getresponse(); print(r.status,r.read(140).decode()); c.close()'
  for path in /health/live/ /health/ready/ /health/dependencies/; do
    docker exec "$container" python -c "$probe" "$path" || true
  done
  nsenter --target "$pid" --net ip -4 -o addr show scope global | awk 'NR==1 {print $4}'
done
ips="$(aws ec2 describe-network-interfaces --region eu-north-1 --filters 'Name=description,Values=ELB app/amaris-staging-alb/c14bdf486b43a0fb' --query 'NetworkInterfaces[?Status==`in-use`].PrivateIpAddress' --output text)"
for ip in $ips; do
  if [[ ! "$ip" =~ ^10\.86\.0\.[0-9]+$ ]]; then continue; fi
  for path in /health/live/ /health/ready/ /health/dependencies/; do
    printf '\n%s%s\n' "$ip" "$path"
    curl -sS --connect-timeout 3 --max-time 8 -H 'Host: 16.171.164.5' -D - "http://$ip$path" | sed -n '1,9p' || true
  done
done
