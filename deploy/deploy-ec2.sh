#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

region="${1:?AWS region required}"
registry="${2:?ECR registry required}"
tag="${3:?Commit SHA required}"
[[ "$region" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]] || exit 2
[[ "$registry" =~ ^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com$ ]] || exit 2
[[ "$tag" =~ ^[a-f0-9]{40}$ ]] || exit 2
root=/home/ec2-user/bekoo
release="$root/releases/$tag"
cd "$release"
test -s .env
chmod 600 .env
command -v aws >/dev/null
docker compose version >/dev/null
exec 9>"$root/deploy.lock"
flock -n 9 || { echo "Another deployment is running"; exit 1; }

export ECR_REGISTRY="$registry" IMAGE_TAG="$tag"
compose() {
  docker compose --project-name bekoo --env-file "$release/.env" -f "$release/compose.aws.yml" "$@"
}
compose config --quiet
aws ecr get-login-password --region "$region" |
  docker login --username AWS --password-stdin "$registry"
compose pull

previous=""
if [[ -f "$root/current-release" ]]; then
  read -r previous < "$root/current-release"
  [[ "$previous" =~ ^[a-f0-9]{40}$ ]] || exit 2
fi
rollback() {
  if [[ -n "$previous" && -s "$root/releases/$previous/.env" ]]; then
    echo "Deployment failed; restoring previous application images"
    IMAGE_TAG="$previous" docker compose --project-name bekoo \
      --env-file "$root/releases/$previous/.env" \
      -f "$root/releases/$previous/compose.aws.yml" \
      up -d --no-deps --wait --wait-timeout 300 booking-care-query booking-care-command ||
      echo "Rollback failed; operator intervention required"
  else
    echo "No previous successful release is available for rollback"
  fi
}
if ! compose up -d --wait --wait-timeout 300 mysql redis kafka elasticsearch bekoo-ai; then
  echo "Infrastructure is not healthy; application deployment stopped"
  exit 1
fi
if ! compose up -d --no-deps --wait --wait-timeout 300 booking-care-query; then
  rollback
  exit 1
fi
if ! compose up -d --no-deps --wait --wait-timeout 300 booking-care-command; then
  rollback
  exit 1
fi
printf '%s\n' "$tag" > "$root/current-release"
compose ps
echo "Deployment healthy: $tag"
# Keep volumes, previous releases and rollback images.
