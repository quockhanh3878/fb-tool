#!/usr/bin/env bash
set -euo pipefail

run_id="commhunter-tests-$(date +%s)-$$"
image="$run_id:local"
builder="$run_id-builder"
container="$run_id-run"

cleanup() {
    result=$?
    for name in "$container" "$container-smoke"; do
        if docker container inspect "$name" >/dev/null 2>&1; then
            docker rm -f "$name" >/dev/null || result=1
        fi
    done
    if docker image inspect "$image" >/dev/null 2>&1; then
        docker image rm "$image" >/dev/null || result=1
    fi
    if docker buildx inspect "$builder" >/dev/null 2>&1; then
        docker buildx rm "$builder" >/dev/null || result=1
    fi
    if docker container inspect "$container" >/dev/null 2>&1 ||
        docker container inspect "$container-smoke" >/dev/null 2>&1 ||
        docker image inspect "$image" >/dev/null 2>&1 ||
        docker buildx inspect "$builder" >/dev/null 2>&1; then
        printf 'Cleanup incomplete for test run %s\n' "$run_id" >&2
        result=1
    fi
    exit "$result"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker buildx create --name "$builder" --driver docker-container >/dev/null
docker buildx build --builder "$builder" --load --target test \
    --file backend/Dockerfile --tag "$image" .
docker run --rm --name "$container" --network none --read-only \
    --tmpfs /tmp:rw,nosuid,size=256m "$image"
docker run --rm --name "$container-smoke" --network none --read-only \
    --tmpfs /tmp:rw,nosuid,size=64m "$image" sh -c \
    'python -m pip check && python -c "from app.workers.browser_runtime import load_phase1_modules; load_phase1_modules()"'