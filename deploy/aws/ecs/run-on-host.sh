#!/usr/bin/env bash
set -euo pipefail

instance="$1"
script="$2"
shift 2
[[ "$instance" =~ ^i-[0-9a-f]+$ ]]
script_base64="$(base64 -w0 "$script")"
command="printf '%s' '$script_base64' | base64 -d | bash -s --"
for argument in "$@"; do
  [[ "$argument" =~ ^[A-Za-z0-9./_-]+$ ]]
  command+=" '$argument'"
done
parameters="$(jq -cn --arg command "$command" '{commands:[$command],executionTimeout:["300"]}')"
id="$(aws ssm send-command --instance-ids "$instance" --document-name AWS-RunShellScript \
  --parameters "$parameters" --timeout-seconds 90 --comment 'Manage Amaris ECS staging host' \
  --query Command.CommandId --output text)"
for attempt in {1..48}; do
  result="$(aws ssm get-command-invocation --command-id "$id" --instance-id "$instance" --output json 2>/dev/null || true)"
  status="$(jq -r .Status <<< "$result")"
  case "$status" in
    Success) jq -r .StandardOutputContent <<< "$result"; exit 0 ;;
    ''|Pending|InProgress|Delayed) sleep 8 ;;
    *)
      printf 'The staging host command returned %s.\n' "$status" >&2
      jq -r '.StandardErrorContent' <<< "$result" >&2
      exit 1
      ;;
  esac
done
echo 'Timed out waiting for the Amaris ECS staging host command.' >&2
exit 1
