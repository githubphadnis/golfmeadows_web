#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f deployment/.env ]]; then
  echo "deployment/.env not found."
  echo "Copy deployment/.env.example to deployment/.env and fill values first."
  exit 1
fi

set -a
source deployment/.env
set +a

if [[ -z "${DOCKER_IMAGE:-}" ]]; then
  echo "DOCKER_IMAGE is required in deployment/.env"
  exit 1
fi

if [[ -z "${HOST_DATA_PATH:-}" ]]; then
  echo "HOST_DATA_PATH is required in deployment/.env"
  exit 1
fi

mkdir -p "${HOST_DATA_PATH}"

echo "Pulling latest image: ${DOCKER_IMAGE}"
docker compose --env-file deployment/.env -f deployment/docker-compose.portainer.yml pull

echo "Starting/updating stack"
docker compose --env-file deployment/.env -f deployment/docker-compose.portainer.yml up -d

echo "Deployment complete."
echo "Health check:"
curl -fsS "http://127.0.0.1:${HOST_PORT:-4173}/api/health" || true
