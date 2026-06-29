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

sanitize_instance_name() {
  local name="$1"

  name="$(printf '%s' "${name}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
  printf '%s\n' "${name}"
}

sanitize_llm_provider() {
  local provider="$1"

  provider="$(printf '%s' "${provider}" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z')"
  case "${provider}" in
    *openai*)
      printf 'openai\n'
      ;;
    *gemini*)
      printf 'gemini\n'
      ;;
    *anthropic*|*claude*)
      printf 'anthropic\n'
      ;;
    *)
      printf 'anthropic\n'
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

  read -r -p "${prompt} [y/N] " response </dev/tty
  [[ "${response}" =~ ^([yY]|[yY][eE][sS])$ ]]
}

read_from_tty() {
  local prompt="$1"
  local value

  if [[ ! -r /dev/tty ]]; then
    die "Interactive input requires a TTY. Run from an SSH terminal or provide values through environment variables."
  fi

  read -r -p "${prompt}" value </dev/tty
  printf '%s\n' "${value}"
}

prompt_value() {
  local variable_name="$1"
  local prompt="$2"
  local default_value="${3:-}"
  local value

  if [[ -n "${!variable_name:-}" ]]; then
    printf '%s\n' "${!variable_name}"
    return
  fi

  if [[ -n "${default_value}" ]]; then
    value="$(read_from_tty "${prompt} [${default_value}]: ")"
    printf '%s\n' "${value:-${default_value}}"
  else
    value="$(read_from_tty "${prompt}: ")"
    printf '%s\n' "${value}"
  fi
}

prompt_required() {
  local variable_name="$1"
  local prompt="$2"
  local value

  while true; do
    value="$(prompt_value "${variable_name}" "${prompt}")"
    if [[ -n "${value}" ]]; then
      printf '%s\n' "${value}"
      return
    fi
    printf '[natursavebot] Value is required\n' >&2
  done
}

prompt_bool() {
  local variable_name="$1"
  local prompt="$2"
  local default_value="${3:-true}"
  local value
  local suffix="[Y/n]"

  if [[ -n "${!variable_name:-}" ]]; then
    value="${!variable_name}"
  else
    if [[ "${default_value}" != "true" ]]; then
      suffix="[y/N]"
    fi
    value="$(read_from_tty "${prompt} ${suffix} ")"
    value="${value:-${default_value}}"
  fi

  case "${value}" in
    true|TRUE|True|1|yes|YES|Yes|y|Y)
      printf 'true\n'
      ;;
    *)
      printf 'false\n'
      ;;
  esac
}

generate_encryption_key() {
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY'
import base64
import os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
PY
    return
  fi

  if command -v python >/dev/null 2>&1; then
    python - <<'PY'
import base64
import os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
PY
    return
  fi

  require_command openssl
  openssl rand -base64 32 | tr '+/' '-_'
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

write_instance_env() {
  local destination="$1"
  local force="${2:-0}"
  local bot_token
  local bot_username
  local owner_id
  local superadmin_id
  local timezone
  local data_dir
  local media_dir
  local save_media
  local max_media_size_mb
  local llm_provider
  local anthropic_api_key
  local openai_api_key
  local gemini_api_key
  local encryption_key

  if [[ -f "${destination}" ]]; then
    if [[ "${force}" -eq 1 ]]; then
      log "Overwriting ${destination}"
    elif ! confirm "Overwrite existing .env at ${destination}?"; then
      die "Keeping existing .env; no overwrite performed"
    fi
  fi

  bot_token="$(prompt_required BOT_TOKEN "BOT_TOKEN from @BotFather")"
  bot_username="$(prompt_value BOT_USERNAME "BOT_USERNAME without @ (optional)")"
  owner_id="$(prompt_required OWNER_TELEGRAM_ID "OWNER_TELEGRAM_ID")"
  superadmin_id="$(prompt_value SUPERADMIN_ID "SUPERADMIN_ID" "${owner_id}")"
  timezone="$(prompt_value TIMEZONE "TIMEZONE" "Europe/Moscow")"
  data_dir="$(prompt_value DATA_DIR "DATA_DIR inside container" "data")"
  media_dir="$(prompt_value MEDIA_DIR "MEDIA_DIR inside container" "${data_dir}/media")"
  save_media="$(prompt_bool SAVE_MEDIA_ENABLED "Enable SAVE_MEDIA" "true")"
  max_media_size_mb="$(prompt_value MAX_MEDIA_SIZE_MB "MAX_MEDIA_SIZE_MB" "50")"
  llm_provider="$(sanitize_llm_provider "$(prompt_value LLM_PROVIDER "LLM_PROVIDER (anthropic/openai/gemini)" "anthropic")")"
  anthropic_api_key="$(prompt_value ANTHROPIC_API_KEY "ANTHROPIC_API_KEY (optional)")"
  openai_api_key="$(prompt_value OPENAI_API_KEY "OPENAI_API_KEY (optional)")"
  gemini_api_key="$(prompt_value GEMINI_API_KEY "GEMINI_API_KEY (optional)")"
  encryption_key="$(generate_encryption_key)"

  install -m 0755 -d "$(dirname -- "${destination}")"
  cat > "${destination}" <<EOF
BOT_TOKEN=${bot_token}
BOT_USERNAME=${bot_username}
OWNER_TELEGRAM_ID=${owner_id}
SUPERADMIN_ID=${superadmin_id}
ENCRYPTION_KEY=${encryption_key}

PROJECT_NAME=Mnemora
TELEGRAM_MODE=business
TIMEZONE=${timezone}
DATABASE_URL=sqlite+aiosqlite:///${data_dir}/app.db
DATA_DIR=${data_dir}
MEDIA_DIR=${media_dir}

SAVE_MODE_ENABLED=true
SAVE_MODE_SCOPE=private
SAVE_MEDIA_ENABLED=${save_media}
SAVE_MEDIA=${save_media}
MAX_MEDIA_SIZE_MB=${max_media_size_mb}
SAVE_MEDIA_MAX_MB=${max_media_size_mb}
NOTIFY_DELETES=true
NOTIFY_EDITS=true
SAVE_MODE_NOTIFY_DELETES=true
SAVE_MODE_NOTIFY_EDITS=true

ENABLE_DOT_COMMANDS=true
ENABLE_GROUP_DOT_COMMANDS=false
ENABLE_HARD_MUTE=true
HARD_MUTE_DELETE_FOR_EVERYONE=true
ENABLE_GROUP_HARD_MUTE=false

ENABLE_SPAM_ALIAS=true
MAX_REPEAT_COUNT=5
REPEAT_DELAY_SECONDS=1.0
REPEAT_DELAY_MIN_SECONDS=0.6
REPEAT_DELAY_MAX_SECONDS=1.4
ENABLE_GROUP_REPEAT=false
DOT_COMMAND_COOLDOWN_SECONDS=30
TYPE_MAX_TEXT_LENGTH=4096
LOVE_ANIMATION_MAX_MESSAGES=5

LLM_PROVIDER=${llm_provider}
ANTHROPIC_API_KEY=${anthropic_api_key}
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
OPENAI_API_KEY=${openai_api_key}
OPENAI_MODEL=gpt-4o-mini
OPENAI_TRANSCRIBE_MODEL=whisper-1
GEMINI_API_KEY=${gemini_api_key}
GEMINI_MODEL=gemini-1.5-flash

MAX_CONTEXT_MESSAGES=80
MAX_LLM_INPUT_CHARS=12000
MAX_SUMMARY_CHARS=3000
DAILY_LLM_LIMIT=100

AUTO_REPLY_ENABLED=false
AUTO_REPLY_MODE=static
AUTO_REPLY_TEXT=I cannot reply right now. I will write back later.
AUTO_REPLY_COOLDOWN_SECONDS=900
REMINDER_LEAD_MINUTES=[15,60,240,1440]
DIGEST_ENABLED=false
DIGEST_TIME=09:00

IGNORE_ARCHIVED_CHATS=true
SYNC_DIALOG_LIMIT=50
SYNC_MESSAGES_PER_CHAT=40
EOF
  chmod 0600 "${destination}"
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
