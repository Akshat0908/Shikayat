#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
server="ubuntu@54.242.22.145"
key="${SHIKAYAT_SSH_KEY:-$HOME/Desktop/Builders/shikayat-key.pem}"
mkdir -p var
chmod 700 var
ssh_args=(-i "$key" -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$PWD/var/deploy_known_hosts")
[[ -f .env && -f "$key" ]] || { echo 'Missing .env or SSH key' >&2; exit 1; }
git merge-base --is-ancestor 0a33b09 HEAD || { echo 'Visitor isolation commit is missing' >&2; exit 1; }
git check-ignore -q .env && git check-ignore -q "$key" || { echo 'Secrets must be git-ignored' >&2; exit 1; }
python3 - <<'PY'
from pathlib import Path
values={}
for line in Path('.env').read_text().splitlines():
    key, sep, value=line.partition('=')
    if sep: values[key.strip()]=value.strip().strip('"\'')
required=('ADMIN_PASSCODE','OPENAI_API_KEY','USER_EMAIL','USER_EMAIL_APP_PASSWORD','DEMO_COMPANY_EMAIL','DEMO_COMPANY_APP_PASSWORD','AUTOPILOT_ALLOWLIST')
missing=[key for key in required if not values.get(key)]
if missing: raise SystemExit('Missing required .env settings: '+', '.join(missing))
PY
revision="$(git rev-parse HEAD)"
release="/home/ubuntu/shikayat/releases/$revision"
staging="$(mktemp -d "${TMPDIR:-/tmp}/shikayat-deploy.XXXXXX")"
trap 'rm -rf "$staging"' EXIT
echo "Building frontend locally from committed revision $revision..."
git archive HEAD | tar -xf - -C "$staging"
npm --prefix "$staging/frontend" ci
npm --prefix "$staging/frontend" run build
echo 'Installing Docker and Compose if needed...'
ssh "${ssh_args[@]}" "$server" 'set -eu; if ! command -v docker >/dev/null || ! sudo docker compose version >/dev/null 2>&1; then sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2; fi; sudo systemctl enable --now docker; mkdir -p "$HOME/.config/shikayat" "$HOME/shikayat/releases"; chmod 700 "$HOME/.config/shikayat"'
echo "Transferring committed revision $revision..."
ssh "${ssh_args[@]}" "$server" "mkdir -p '$release'"
git archive HEAD | ssh "${ssh_args[@]}" "$server" "tar -xf - -C '$release'"
tar -C "$staging/frontend" -cf - out | ssh "${ssh_args[@]}" "$server" "rm -rf '$release/frontend/out' && tar -xf - -C '$release/frontend'"
echo 'Transferring production configuration securely...'
scp "${ssh_args[@]}" .env "$server:/home/ubuntu/.config/shikayat/production.env.new" >/dev/null
ssh "${ssh_args[@]}" "$server" 'set -eu; file="$HOME/.config/shikayat/production.env.new"; chmod 600 "$file"; sed -i "/^[[:space:]]*PUBLIC_DEMO=/d; /^[[:space:]]*DEMO_MODE=/d" "$file"; printf "\nPUBLIC_DEMO=true\nDEMO_MODE=true\n" >> "$file"; mv "$file" "$HOME/.config/shikayat/production.env"; chmod 600 "$HOME/.config/shikayat/production.env"'
echo 'Building and restarting the production stack...'
ssh "${ssh_args[@]}" "$server" "cd '$release' && sudo docker compose -p shikayat up -d --build --remove-orphans && ln -sfn '$release' /home/ubuntu/shikayat/current"
echo 'Deployment started: https://54-242-22-145.sslip.io'
