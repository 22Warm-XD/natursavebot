#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'USAGE'
Usage: list-instances.sh

Lists Natursavebot instances under /opt/natursavebot.
USAGE
}

main() {
  local found=0
  local directory
  local instance_name
  local status
  local container

  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
  fi

  require_command docker

  printf '%-24s %-16s %-32s %s\n' "INSTANCE" "STATUS" "CONTAINER" "PATH"

  shopt -s nullglob
  for directory in "${INSTALL_ROOT}"/*; do
    [[ -d "${directory}" && -f "${directory}/compose.yml" ]] || continue
    instance_name="$(basename -- "${directory}")"
    container="$(container_name "${instance_name}")"
    status="$(docker inspect -f '{{.State.Status}}' "${container}" 2>/dev/null || printf 'not_created')"
    printf '%-24s %-16s %-32s %s\n' "${instance_name}" "${status}" "${container}" "${directory}"
    found=1
  done
  shopt -u nullglob

  if [[ "${found}" -eq 0 ]]; then
    log "No instances found under ${INSTALL_ROOT}"
  fi
}

main "$@"
