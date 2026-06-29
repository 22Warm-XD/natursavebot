#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'USAGE'
Usage: sudo update-instance.sh INSTANCE_NAME [--source PATH] [--no-start]

Refreshes the app source snapshot for an existing instance and rebuilds its
Docker image. Existing .env files are preserved.
USAGE
}

main() {
  local instance_name=""
  local source_arg=""
  local source_dir
  local directory
  local start_container=1

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source)
        [[ $# -ge 2 ]] || die "--source requires a path"
        source_arg="$2"
        shift 2
        ;;
      --no-start)
        start_container=0
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      -*)
        die "Unknown option: $1"
        ;;
      *)
        [[ -z "${instance_name}" ]] || die "Only one INSTANCE_NAME is supported"
        instance_name="$1"
        shift
        ;;
    esac
  done

  [[ -n "${instance_name}" ]] || die "INSTANCE_NAME is required"
  validate_instance_name "${instance_name}"
  ensure_docker_compose
  ensure_instance_exists "${instance_name}"

  source_dir="$(resolve_source_dir "${source_arg}")"
  check_source_dir "${source_dir}"

  directory="$(instance_dir "${instance_name}")"
  sync_app_source "${source_dir}" "${directory}/app"
  write_compose_file "${instance_name}"

  if [[ ! -f "${directory}/.env" ]]; then
    log "No .env found for '${instance_name}', creating one from .env.example"
    write_env_from_template "${source_dir}/.env.example" "${directory}/.env" 0
  fi

  if [[ "${start_container}" -eq 1 ]]; then
    compose_for_instance "${instance_name}" up -d --build
  else
    compose_for_instance "${instance_name}" build
    log "Instance '${instance_name}' updated without starting the container"
  fi

  log "Instance '${instance_name}' updated at ${directory}"
}

main "$@"
