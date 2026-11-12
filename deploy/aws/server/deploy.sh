#!/usr/bin/env bash
# EC2: deploy both CQRS services at one SHA; runtime env files are never sourced.
set -Eeuo pipefail
umask 077
APP=${1:?app name required}
SHA=${2:?40-character git SHA required}
[[ "$APP" =~ ^[a-z0-9][a-z0-9-]{1,62}$ && "$SHA" =~ ^[0-9a-f]{40}$ ]] || exit 2
DIR="${APPS_ROOT:-/opt/apps}/$APP"
cd "$DIR"
exec 9> .deploy.lock
flock -x 9
field() { sed -n "s/^$1=//p" release.env | tail -n 1; }
PREFIX=$(field IMAGE_PREFIX)
COMMAND_PORT=$(field COMMAND_HOST_PORT)
QUERY_PORT=$(field QUERY_HOST_PORT)
[[ "$PREFIX" =~ ^[0-9]{12}\.dkr\.ecr\.([a-z]{2}(-[a-z]+)+-[0-9]+)\.amazonaws\.com$ ]] || exit 2
REGION=${BASH_REMATCH[1]}
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$PREFIX"
# Reuse the pre-provisioned bridge; never recreate database infrastructure during CD.
network=$(docker network inspect bekoo-backend)
jq -e '.[0].Driver == "bridge" and .[0].IPAM.Config[0].Subnet == "172.30.83.0/24" and .[0].IPAM.Config[0].Gateway == "172.30.83.1"' <<< "$network" >/dev/null
python3 "$DIR/check-mysql.py" "$DIR"
for port in "$COMMAND_PORT" "$QUERY_PORT"; do
  [[ "$port" =~ ^[0-9]{2,5}$ ]] && ((10#$port > 0 && 10#$port < 65536)) || exit 2
done
[[ "$COMMAND_PORT" != "$QUERY_PORT" ]] || exit 2
compose() {
  env -u IMAGE_PREFIX -u IMAGE_TAG -u COMMAND_HOST_PORT -u QUERY_HOST_PORT \
    -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_PROFILES \
    docker compose -p "$APP" --env-file "$DIR/release.env" -f "$DIR/compose.yaml" "$@"
}
write_release() {
  local tmp
  tmp=$(mktemp "$DIR/.release.XXXXXX")
  printf 'IMAGE_PREFIX=%s\nIMAGE_TAG=%s\nCOMMAND_HOST_PORT=%s\nQUERY_HOST_PORT=%s\n' \
    "$PREFIX" "$1" "$COMMAND_PORT" "$QUERY_PORT" > "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" release.env
}
revision() {
  local container image
  container=$(compose ps -q "$1")
  [[ -n "$container" ]] || return 1
  image=$(docker inspect -f '{{.Image}}' "$container")
  docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image"
}
healthy_port() {
  local port="$1" attempt
  for ((attempt=0; attempt<90; attempt++)); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$port/actuator/health" 2>/dev/null \
      | jq -e '.status == "UP"' >/dev/null; then return 0; fi
    sleep 5
  done
  return 1
}
healthy() { healthy_port "$COMMAND_PORT" && healthy_port "$QUERY_PORT"; }
start_backends() {
  compose up -d --no-build --no-deps --force-recreate command || return 1
  healthy_port "$COMMAND_PORT" || return 1
  compose up -d --no-build --no-deps --force-recreate query || return 1
  healthy_port "$QUERY_PORT" || return 1
}
verify_images() {
  local service container actual expected label
  for service in command query; do
    expected=$(docker image inspect -f '{{.Id}}' "$PREFIX/bekoo-$service:$1") || return 1
    label=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$expected") || return 1
    [[ "$label" == "$1" ]] || return 1
    container=$(compose ps -q "$service") || return 1
    [[ -n "$container" ]] || return 1
    actual=$(docker inspect -f '{{.Image}}' "$container") || return 1
    [[ "$actual" == "$expected" ]] || return 1
  done
}
# Both old revisions must agree; never infer a rollback SHA from release.env.
OLD=$(revision command || true)
OLD_QUERY=$(revision query || true)
if [[ ! "$OLD" =~ ^[0-9a-f]{40}$ || "$OLD" != "$OLD_QUERY" ]]; then OLD=''; fi
# Pull and validate BOTH images before modifying either running backend.
for service in command query; do
  docker pull "$PREFIX/bekoo-$service:$SHA"
  label=$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$PREFIX/bekoo-$service:$SHA")
  [[ "$label" == "$SHA" ]] || { echo "Revision mismatch: $service" >&2; exit 1; }
done
rollback() {
  trap - ERR INT TERM
  if [[ -z "$OLD" || "$OLD" == "$SHA" ]]; then
    echo 'Deploy failed; no different coherent prior release. Manual recovery required.' >&2
    exit 1
  fi
  echo "Rolling back both backends to $OLD" >&2
  for service in command query; do
    docker image inspect "$PREFIX/bekoo-$service:$OLD" >/dev/null 2>&1 \
      || docker pull "$PREFIX/bekoo-$service:$OLD" || { echo 'ROLLBACK FAILED: image unavailable' >&2; exit 1; }
  done
  if [[ -n "${ROLLBACK_ENV_DIR:-}" ]]; then
    for file in command.env query.env; do
      if [[ -f "$ROLLBACK_ENV_DIR/$file" ]]; then install -m 600 "$ROLLBACK_ENV_DIR/$file" "$DIR/$file"; fi
    done
  fi
  write_release "$OLD"
  if start_backends && verify_images "$OLD" && healthy; then
    echo "Rollback healthy: $OLD" >&2
  else
    echo 'ROLLBACK FAILED: manual recovery required' >&2
  fi
  exit 1
}
# Infrastructure failure must not change release.env or restart old backends.
compose up -d --wait --wait-timeout 240 kafka redis elasticsearch
trap rollback ERR INT TERM
write_release "$SHA"
start_backends
verify_images "$SHA"
healthy
trap - ERR INT TERM
printf '%s %s\n' "$(date -u +%FT%TZ)" "$SHA" >> releases.log
echo "Deploy success: $APP $SHA"
