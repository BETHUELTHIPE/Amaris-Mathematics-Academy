#!/usr/bin/env bash
set -euo pipefail
printf 'Host memory and CPU credit relevant load:\n'
free -m
uptime
printf 'Containers persistently running:\n'
docker ps --format '{{.Names}} {{.Status}}'
printf 'ECS application-container health status codes:\n'
for family in amaris-ecs-staging-private-web amaris-ecs-staging-alb-web; do
  for component in frontend backend valkey; do
    id="$(docker ps -q --filter "label=com.amazonaws.ecs.task-definition-family=$family" --filter "label=com.amazonaws.ecs.container-name=$component")"
    if [[ "$id" =~ ^[a-f0-9]{12,64}$ ]]; then
      printf '%s %s ' "$family" "$component"
      docker inspect --format '{{.State.Health.Status}} retries={{.State.Health.FailingStreak}} exits={{range .State.Health.Log}}{{.ExitCode}} {{end}}' "$id"
    fi
  done
done
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
  docker exec "$container" python -c '
import os, socket, time, urllib.parse
import psycopg
url=urllib.parse.urlsplit(os.environ["AMARIS_RUNTIME_ENV"].split("DATABASE_URL=", 1)[1].splitlines()[0])
print("Postgres endpoint type", "pooler" if (url.hostname or "").endswith(".pooler.supabase.com") else "direct", "port",url.port)
for host in sorted({entry[4][0] for entry in socket.getaddrinfo(url.hostname,url.port,socket.AF_INET,socket.SOCK_STREAM)}):
 print("Pooler IPv4",host)
 for attempt in range(4):
  try:
   with psycopg.connect(host=url.hostname,hostaddr=host,port=url.port,dbname=url.path.lstrip("/"),user=urllib.parse.unquote(url.username),password=urllib.parse.unquote(url.password),connect_timeout=4,sslmode="require") as conn:
    conn.execute("SELECT 1")
   print("Read-only connection succeeded.")
  except (psycopg.Error,OSError) as error:
   description=str(error).lower()
   reasons=[word for word in ("too many","timed out","timeout","no route","refused","closed the connection","authentication failed","max client","could not translate","remaining connection slots","session mode") if word in description]
   print("Read-only connection failed",type(error).__name__,getattr(error,"sqlstate",None),"/".join(reasons))
  time.sleep(.3)
' || true
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
