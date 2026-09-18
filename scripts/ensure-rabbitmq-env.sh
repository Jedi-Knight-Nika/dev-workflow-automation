#!/bin/sh
set -eu

env_file="${1:-.env}"
[ -f "$env_file" ] && [ ! -L "$env_file" ] || {
  echo "Create a regular $env_file from the environment example first." >&2
  exit 1
}
if [ -n "${RABBITMQ_USER+x}${RABBITMQ_PASSWORD+x}${RABBITMQ_URL+x}" ]; then
  [ -n "${RABBITMQ_USER:-}" ] && [ -n "${RABBITMQ_PASSWORD:-}" ] && [ -n "${RABBITMQ_URL:-}" ] || {
    echo "Supply all three RabbitMQ environment variables, or unset them to use $env_file." >&2
    exit 1
  }
  exit 0
fi

umask 077
lock="$env_file.rabbitmq-lock"
mkdir "$lock" 2>/dev/null || {
  echo "RabbitMQ configuration is already being initialized: $lock" >&2
  exit 1
}
temporary=""
trap 'rm -f "$temporary"; rmdir "$lock"' EXIT
trap 'exit 1' HUP INT TERM

state=$(awk '
  /^[[:space:]]*(export[[:space:]]+)?RABBITMQ_(USER|PASSWORD|URL)[[:space:]]*=/ {
    line = $0
    sub(/^[[:space:]]*(export[[:space:]]+)?/, "", line)
    key = line
    sub(/[[:space:]]*=.*/, "", key)
    sub(/^[^=]*=[[:space:]]*/, "", line)
    sub(/[[:space:]]+#.*$/, "", line)
    sub(/[[:space:]]+$/, "", line)
    if (line ~ /^#/) line = ""
    if (line ~ /^".*"$/ || line ~ /^\047.*\047$/) line = substr(line, 2, length(line) - 2)
    values[key] = line
  }
  END {
    username = values["RABBITMQ_USER"]
    password = values["RABBITMQ_PASSWORD"]
    url = values["RABBITMQ_URL"]
    placeholder_password = password ~ /^(change-me-before-deployment|replace-with-a-strong-broker-password)$/
    placeholder_url = url ~ /^amqp:\/\/engineering_worker:(change-me-before-deployment|replace-with-a-strong-broker-password)@rabbitmq:5672\/aew$/
    if (username != "" && password != "" && url != "" && !placeholder_password && !placeholder_url) {
      print "configured"
    } else if ((username != "" && username != "engineering_worker") ||
               (password != "" && !placeholder_password) ||
               (url != "" && !placeholder_url)) {
      print "partial"
    } else {
      print "generate"
    }
  }
' "$env_file")
case "$state" in
  configured) exit 0 ;;
  partial)
    echo "RabbitMQ credentials in $env_file are incomplete; preserve the existing values and supply the missing fields." >&2
    exit 1
    ;;
esac

volumes=$(docker volume ls --quiet \
  --filter label=com.docker.compose.project=autonomous-engineering-worker \
  --filter label=com.docker.compose.volume=rabbitmq_data)
[ -z "$volumes" ] || {
  echo "Existing RabbitMQ data found. Restore its credentials in $env_file; refusing to generate a different password." >&2
  exit 1
}
password=$(openssl rand -hex 32)
temporary=$(mktemp "$env_file.rabbitmq.XXXXXX")
awk '!/^[[:space:]]*(export[[:space:]]+)?RABBITMQ_(USER|PASSWORD|URL)[[:space:]]*=/' "$env_file" >"$temporary"
printf '\nRABBITMQ_USER=engineering_worker\nRABBITMQ_PASSWORD=%s\nRABBITMQ_URL=amqp://engineering_worker:%s@rabbitmq:5672/aew\n' \
  "$password" "$password" >>"$temporary"
mv "$temporary" "$env_file"
temporary=""
echo "Initialized local RabbitMQ credentials in $env_file. No external account is needed."
