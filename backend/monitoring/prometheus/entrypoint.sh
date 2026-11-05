#!/bin/sh
set -eu

credentials="$(cat /run/secrets/flower_basic_auth)"
case "$credentials" in
    *:*) ;;
    *)
        echo "FLOWER_BASIC_AUTH must use username:password format." >&2
        exit 1
        ;;
esac

username="${credentials%%:*}"
password="${credentials#*:}"
if [ -z "$username" ] || [ -z "$password" ]; then
    echo "FLOWER_BASIC_AUTH username and password must both be non-empty." >&2
    exit 1
fi

umask 077
printf '%s' "$username" > /tmp/flower_username
printf '%s' "$password" > /tmp/flower_password
unset credentials username password

exec /bin/prometheus "$@"
