#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'USAGE'
Usage: sudo create-instance.sh INSTANCE_NAME [--source PATH] [--no-start] [--force-env]

Creates /opt/natursavebot/INSTANCE_NAME with an independent:
  - app source snapshot
  - .env file
  - data/media directory
  - compose.yml project
  - Docker container

INSTANCE_NAME must use lowercase letters, digits, '-' or '_'.
USAGE
}

main() {
  local instance_name=""
  local source_arg=""
  local source_dir
  local directory
  local force_env=0
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
      --force-env)
        force_env=1
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

  source_dir="$(resolve_source_dir "${source_arg}")"
  check_source_dir "${source_dir}"

  directory="$(instance_dir "${instance_name}")"
  assert_under_install_root "${directory}"

  if [[ -f "${directory}/compose.yml" ]]; then
    die "Instance '${instance_name}' already exists. Use update-instance.sh to update it."
  fi

  install -m 0755 -d "${directory}" "${directory}/data" "${directory}/data/media"
  sync_app_source "${source_dir}" "${directory}/app"
  write_compose_file "${instance_name}"
  write_env_from_template "${source_dir}/.env.example" "${directory}/.env" "${force_env}"

  if [[ "${start_container}" -eq 1 ]]; then
    compose_for_instance "${instance_name}" up -d --build
  else
    log "Instance '${instance_name}' created without starting the container"
  fi

  log "Instance '${instance_name}' is ready at ${directory}"
}

main "$@"
