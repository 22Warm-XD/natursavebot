#!/usr/bin/env bash

INSTALL_ROOT="${NATURSAVEBOT_ROOT:-/opt/natursavebot}"
PROJECT_PREFIX="${NATURSAVEBOT_PROJECT_PREFIX:-natursavebot}"

log() {
  printf '[natursavebot] %s\n' "$*"
}

die() {
  printf '[natursavebot] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  local command_name="$1"

  command -v "${command_name}" >/dev/null 2>&1 || die "Required command is missing: ${command_name}"
}

ensure_docker_compose() {
  require_command docker
  docker compose version >/dev/null 2>&1 || die "Docker Compose plugin is required. Install docker-compose-plugin."
}

validate_instance_name() {
  local name="$1"

  if [[ ! "${name}" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]]; then
    die "Invalid instance name '${name}'. Use lowercase letters, digits, '-' or '_', starting with a letter or digit."
  fi

  case "${name}" in
    app|bin|scripts|data|media|root)
      die "Instance name '${name}' is reserved"
      ;;
  esac
}

instance_dir() {
  local name="$1"

  printf '%s/%s\n' "${INSTALL_ROOT}" "${name}"
}

compose_project() {
  local name="$1"

  printf '%s_%s\n' "${PROJECT_PREFIX}" "${name}"
}

container_name() {
  local name="$1"

  printf '%s-%s\n' "${PROJECT_PREFIX}" "${name}"
}

confirm() {
  local prompt="$1"
  local response

  read -r -p "${prompt} [y/N] " response
  [[ "${response}" =~ ^([yY]|[yY][eE][sS])$ ]]
}

assert_under_install_root() {
  local path="$1"
  local resolved_root
  local resolved_path

  resolved_root="$(realpath -m -- "${INSTALL_ROOT}")"
  resolved_path="$(realpath -m -- "${path}")"

  case "${resolved_path}" in
    "${resolved_root}"/*)
      ;;
    *)
      die "Refusing to operate outside ${resolved_root}: ${resolved_path}"
      ;;
  esac
}

default_source_dir() {
  local script_dir

  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[1]}")" && pwd)"

  if [[ -f "${script_dir}/../Dockerfile" && -d "${script_dir}/../src" ]]; then
    realpath -- "${script_dir}/.."
  else
    printf '%s/app\n' "${INSTALL_ROOT}"
  fi
}

resolve_source_dir() {
  local requested="${1:-}"

  if [[ -n "${requested}" ]]; then
    realpath -- "${requested}"
  else
    default_source_dir
  fi
}

check_source_dir() {
  local source_dir="$1"
  local required

  for required in Dockerfile requirements.txt .env.example src; do
    [[ -e "${source_dir}/${required}" ]] || die "Source directory is missing ${required}: ${source_dir}"
  done
}

sync_app_source() {
  local source_dir="$1"
  local target_dir="$2"
  local file

  check_source_dir "${source_dir}"
  assert_under_install_root "${target_dir}"

  install -m 0755 -d "${target_dir}"
  rm -rf -- "${target_dir}/src"
  install -m 0755 -d "${target_dir}/src"
  cp -a "${source_dir}/src/." "${target_dir}/src/"
  find "${target_dir}/src" -type d -name '__pycache__' -prune -exec rm -rf -- {} +
  find "${target_dir}/src" -type f -name '*.pyc' -delete

  for file in Dockerfile requirements.txt README.md .env.example LICENSE; do
    if [[ -f "${source_dir}/${file}" ]]; then
      install -m 0644 "${source_dir}/${file}" "${target_dir}/${file}"
    fi
  done
}

write_compose_file() {
  local name="$1"
  local directory
  local compose_file

  directory="$(instance_dir "${name}")"
  compose_file="${directory}/compose.yml"

  install -m 0755 -d "${directory}"
  cat > "${compose_file}" <<EOF
name: $(compose_project "${name}")
services:
  bot:
    build:
      context: ./app
    image: $(container_name "${name}"):latest
    container_name: $(container_name "${name}")
    restart: unless-stopped
    env_file:
      - ./.env
    volumes:
      - ./data:/app/data
    command: python -m src.main
EOF
}

write_env_from_template() {
  local template="$1"
  local destination="$2"
  local force="${3:-0}"

  if [[ -f "${destination}" ]]; then
    if [[ "${force}" -eq 1 ]]; then
      log "Overwriting ${destination}"
    elif ! confirm "Overwrite existing .env at ${destination}?"; then
      die "Keeping existing .env; no overwrite performed"
    fi
  fi

  install -m 0600 "${template}" "${destination}"
}

ensure_instance_exists() {
  local name="$1"
  local directory

  directory="$(instance_dir "${name}")"
  [[ -d "${directory}" && -f "${directory}/compose.yml" ]] || die "Instance '${name}' does not exist at ${directory}"
}

compose_for_instance() {
  local name="$1"
  local directory

  shift
  directory="$(instance_dir "${name}")"

  docker compose \
    --project-name "$(compose_project "${name}")" \
    --project-directory "${directory}" \
    --file "${directory}/compose.yml" \
    "$@"
}
