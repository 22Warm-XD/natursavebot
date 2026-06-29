#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${SCRIPT_PATH}")" && pwd)"
REPO_TARBALL_URL="${NATURSAVEBOT_TARBALL_URL:-https://github.com/22Warm-XD/natursavebot/archive/refs/heads/main.tar.gz}"
OS_ID=""
OS_VERSION_CODENAME=""

bootstrap_from_tarball_if_needed() {
  local temp_dir

  if [[ -f "${SCRIPT_DIR}/scripts/lib.sh" && -d "${SCRIPT_DIR}/src" ]]; then
    return
  fi

  command -v curl >/dev/null 2>&1 || {
    printf '[natursavebot] ERROR: curl is required for pipe installation\n' >&2
    exit 1
  }
  command -v tar >/dev/null 2>&1 || {
    printf '[natursavebot] ERROR: tar is required for pipe installation\n' >&2
    exit 1
  }

  temp_dir="$(mktemp -d)"
  printf '[natursavebot] Downloading installer bundle from GitHub\n'
  curl -fsSL "${REPO_TARBALL_URL}" | tar -xz -C "${temp_dir}" --strip-components=1
  exec bash "${temp_dir}/install.sh" "$@"
}

bootstrap_from_tarball_if_needed "$@"

# shellcheck source=scripts/lib.sh
source "${SCRIPT_DIR}/scripts/lib.sh"

usage() {
  cat <<'USAGE'
Usage: sudo ./install.sh [--root /opt/natursavebot] [--skip-docker-install] [--no-create-instance]

Installs Natursavebot production helpers on Ubuntu/Debian:
  - Docker Engine with the Docker Compose plugin when needed
  - app source snapshot under /opt/natursavebot/app
  - multi-instance scripts under /opt/natursavebot/bin
  - convenience commands under /usr/local/bin

This installer never copies .env secrets into /opt/natursavebot/app.
By default it asks for instance settings and starts the first bot instance.
USAGE
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      log "Root privileges are required; re-running through sudo"
      exec sudo -E bash "${SCRIPT_DIR}/install.sh" "$@"
    fi
    die "Run this installer as root, for example: curl -fsSL https://raw.githubusercontent.com/22Warm-XD/natursavebot/main/install.sh | sudo bash"
  fi
}

load_os_release() {
  if [[ ! -r /etc/os-release ]]; then
    die "Cannot detect OS: /etc/os-release is missing"
  fi

  # shellcheck disable=SC1091
  source /etc/os-release

  OS_ID="${ID:-}"
  OS_VERSION_CODENAME="${VERSION_CODENAME:-}"

  if [[ "${OS_ID}" != "ubuntu" && "${OS_ID}" != "debian" ]]; then
    die "Unsupported OS '${OS_ID:-unknown}'. This installer supports Ubuntu/Debian."
  fi

  if [[ -z "${OS_VERSION_CODENAME}" ]]; then
    die "Cannot detect Debian/Ubuntu codename from /etc/os-release"
  fi
}

install_docker_repo() {
  local keyring="/etc/apt/keyrings/docker.gpg"
  local list_file="/etc/apt/sources.list.d/docker.list"
  local arch

  arch="$(dpkg --print-architecture)"

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" | gpg --dearmor -o "${keyring}"
  chmod a+r "${keyring}"

  printf 'deb [arch=%s signed-by=%s] https://download.docker.com/linux/%s %s stable\n' \
    "${arch}" "${keyring}" "${OS_ID}" "${OS_VERSION_CODENAME}" > "${list_file}"
}

install_docker_stack() {
  load_os_release

  log "Installing apt prerequisites"
  apt-get update
  apt-get install -y ca-certificates curl gnupg

  if docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin is already available"
    return
  fi

  log "Installing Docker Engine and Docker Compose plugin from Docker's apt repository"
  install_docker_repo
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  if command -v systemctl >/dev/null 2>&1; then
    systemctl enable --now docker || log "Docker service could not be enabled automatically; check systemctl status docker"
  fi

  docker compose version >/dev/null
}

install_app_snapshot() {
  local app_dir="${INSTALL_ROOT}/app"

  log "Installing app snapshot into ${app_dir}"
  install -m 0755 -d "${INSTALL_ROOT}" "${INSTALL_ROOT}/bin" "${app_dir}"
  sync_app_source "${SCRIPT_DIR}" "${app_dir}"
}

install_helper_scripts() {
  local script

  log "Installing multi-instance scripts into ${INSTALL_ROOT}/bin"
  for script in create-instance.sh update-instance.sh remove-instance.sh list-instances.sh; do
    install -m 0755 "${SCRIPT_DIR}/scripts/${script}" "${INSTALL_ROOT}/bin/${script}"
  done
  install -m 0644 "${SCRIPT_DIR}/scripts/lib.sh" "${INSTALL_ROOT}/bin/lib.sh"
  install -m 0755 "${SCRIPT_DIR}/install.sh" "${INSTALL_ROOT}/install.sh"

  ln -sfn "${INSTALL_ROOT}/bin/create-instance.sh" /usr/local/bin/natursavebot-create-instance
  ln -sfn "${INSTALL_ROOT}/bin/update-instance.sh" /usr/local/bin/natursavebot-update-instance
  ln -sfn "${INSTALL_ROOT}/bin/remove-instance.sh" /usr/local/bin/natursavebot-remove-instance
  ln -sfn "${INSTALL_ROOT}/bin/list-instances.sh" /usr/local/bin/natursavebot-list-instances
}

main() {
  local skip_docker_install=0
  local create_instance=1
  local original_args=("$@")

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --root)
        [[ $# -ge 2 ]] || die "--root requires a path"
        INSTALL_ROOT="$2"
        shift 2
        ;;
      --skip-docker-install)
        skip_docker_install=1
        shift
        ;;
      --no-create-instance)
        create_instance=0
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  require_root "${original_args[@]}"

  if [[ "${skip_docker_install}" -eq 0 ]]; then
    install_docker_stack
  else
    require_command docker
    docker compose version >/dev/null || die "Docker Compose plugin is not available"
  fi

  install_app_snapshot
  install_helper_scripts

  if [[ "${create_instance}" -eq 1 ]]; then
    "${INSTALL_ROOT}/bin/create-instance.sh" --source "${INSTALL_ROOT}/app"
  fi

  cat <<EOF

Natursavebot production helpers installed.

Create another instance:
  sudo natursavebot-create-instance main

List instances:
  sudo natursavebot-list-instances

Instance directories live under:
  ${INSTALL_ROOT}/<instance-name>
EOF
}

main "$@"
