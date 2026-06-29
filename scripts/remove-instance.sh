#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
  cat <<'USAGE'
Usage: sudo remove-instance.sh INSTANCE_NAME [--force] [--keep-files]

Stops and removes the Docker Compose project for an instance. By default it
also deletes /opt/natursavebot/INSTANCE_NAME, including data and media.

Without --force, you must type the instance name to confirm deletion.
USAGE
}

confirm_removal() {
  local instance_name="$1"
  local directory="$2"
  local response

  printf 'This will remove instance "%s" at %s, including .env, data, and media.\n' "${instance_name}" "${directory}"
  read -r -p "Type the instance name to continue: " response
  [[ "${response}" == "${instance_name}" ]] || die "Confirmation did not match; aborting"
}

main() {
  local instance_name=""
  local force=0
  local keep_files=0
  local directory

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force)
        force=1
        shift
        ;;
      --keep-files)
        keep_files=1
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

  directory="$(instance_dir "${instance_name}")"
  assert_under_install_root "${directory}"

  if [[ "${force}" -eq 0 && "${keep_files}" -eq 0 ]]; then
    confirm_removal "${instance_name}" "${directory}"
  fi

  compose_for_instance "${instance_name}" down --remove-orphans

  if [[ "${keep_files}" -eq 1 ]]; then
    log "Instance files kept at ${directory}"
  else
    rm -rf -- "${directory}"
    log "Instance '${instance_name}' removed"
  fi
}

main "$@"
