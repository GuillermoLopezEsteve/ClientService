#!/usr/bin/env bash
set -e
GREEN="\033[0;32m";YELLOW="\033[0;33m";RED="\033[0;31m";CYAN="\033[0;36m";NC="\033[0m"
fail()    { echo -e "${RED}[ERROR  ] ${NC}$1"; exit 1; }
success() { echo -e "${GREEN}[SUCCESS] ${NC}$1"; }
warn()    { echo -e "${YELLOW}[WARN   ] ${NC}$1"; }

ORIG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ORIG_DIR/clientservice.env"
[[ -n "${BASH_VERSION:-}" ]] || fail "Must be runned as bash"
[[ $EUID -eq 0 ]] || fail "This script must be run as sudo"
[[ -f "$ENV_FILE" ]] && success "File exists: $ENV_FILE" || fail "File not found: $ENV_FILE"
source $ENV_FILE && success "Load Environment variables" || fail "Failed to load environment"

for v in RUNTIME_DIR WEB_SERVER RUNTIME_ENV LAUNCHER TASKS CRON_LOG TASKS_END_POINT UPDATE_END_POINT PYTHON_PROG BASE_DIR; do
  [[ -n "${!v:-}" ]] || fail "$v is required"
done

mkdir -p $RUNTIME_DIR || fail "Failed to prepare RUNTIME_DIR"
cp $PYTHON_PROG "$RUNTIME_DIR/" || fail "Failed to copy python program"
cp $ENV_FILE "$RUNTIME_DIR/" || fail "Failed to copy python program"
success "Set up runtime DIR"

curl -k $TASKS_END_POINT -o $TASKS || fail "Could not CURL $TASKS_END_POINT"
success "Obtained data from api endpoint"

if [[ "$TEST" = "True" ]]; then
    warn "TESTING MODE"
    ls -l $RUNTIME_DIR || fail "Error in ls -l: $RUNTIME_DIR"
fi

while true; do
    read -p "Which group do you belong to? " GROUP_ID
    if ! [[ "$GROUP_ID" =~ ^[0-9]+$ ]]; then
        echo "Group ID must be a number."
        continue
    fi
    read -p "You entered Group ID '$GROUP_ID'. Is this correct? (y/n): " CONFIRM
    case "$CONFIRM" in
        y|Y)
            break
            ;;
        n|N)
            echo "Let's try again."
            ;;
        *)
            echo "Please answer y or n."
            ;;
    esac
done
success "Confirmed Group ID: $GROUP_ID"
echo "GROUP_ID=${GROUP_ID}" >> "$RUNTIME_ENV"

APT_PACKAGES=( python3 )
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && success "Lists updated" || fail "Apt update failed"
if apt-get install -y -qq "${APT_PACKAGES[@]}" > /dev/null 2>&1; then
    success "System packages installed: ${APT_PACKAGES[*]}"
else
    fail "Failed to install system packages."
fi



LAUNCHER_CMD="*/5 * * * * root /usr/bin/python3 ${LAUNCHER} $GROUP_ID ${TASKS} ${WEB_SERVER} >> ${CRON_LOG} 2>&1"
CURL_CMD="0 0 * * * root /usr/bin/curl -k ${TASKS_END_POINT} -o ${TASKS}"
{
  echo "SHELL=/bin/bash"
  echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  echo "GROUP_ID=${GROUP_ID}"
  echo "$LAUNCHER_CMD"
  echo "$CURL_CMD"
} > "$CRON_FILE" || fail "Failure to write cron job"

chmod 0644 "$CRON_FILE" || fail "Failed to set permissions on $CRON_FILE"

if [[ "$TEST" = "True" ]]; then
    warn "TESTING MODE"
    cat "$CRON_FILE" || fail "Error in cat: $CRON_FILE"
fi

success "Cron job added in $CRON_FILE"





#rm -rf $ORIG_DIR && success "Installtion fully done."
