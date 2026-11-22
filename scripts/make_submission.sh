#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
mkdir -p "$tmp_dir/tree"
git archive HEAD | tar -xf - -C "$tmp_dir/tree"
# Include the complete presentation artifacts, including untracked files if present.
if [[ -d deck ]]; then mkdir -p "$tmp_dir/tree/deck"; cp -R deck/. "$tmp_dir/tree/deck/"; fi
if [[ -f VIDEO.md ]]; then cp VIDEO.md "$tmp_dir/tree/VIDEO.md"; fi
if [[ -f demo/Shikayat-demo.mp4 ]]; then mkdir -p "$tmp_dir/tree/demo"; cp demo/Shikayat-demo.mp4 "$tmp_dir/tree/demo/Shikayat-demo.mp4"; fi
python3 - "$tmp_dir/tree" "$tmp_dir/submission.zip" <<'PY'
import re
import shlex
import sys
import zipfile
from pathlib import Path

root, staging = map(Path, sys.argv[1:])
output = Path.cwd() / 'Shikayat-submission.zip'
env_path = Path.cwd() / '.env'
if not env_path.is_file():
    raise SystemExit('Cannot scan configured secrets: local .env is missing.')
secret_names = {'OPENAI_API_KEY', 'USER_EMAIL_APP_PASSWORD', 'DEMO_COMPANY_APP_PASSWORD', 'ADMIN_PASSCODE'}
secrets = {}
for line in env_path.read_text(encoding='utf-8').splitlines():
    match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$', line)
    if not match or match.group(1) not in secret_names:
        continue
    name, raw = match.groups()
    raw = raw.strip()
    if raw.startswith(('"', "'")):
        try:
            parsed = shlex.split(raw, comments=True)
        except ValueError:
            raise SystemExit(f'Cannot parse {name} in local .env; no archive created.')
        value = parsed[0] if parsed else ''
    else:
        value = re.split(r'\s+#', raw, maxsplit=1)[0].rstrip()
    if value:
        secrets[name] = value.encode('utf-8')
        if name.endswith('_APP_PASSWORD'):
            compact = re.sub(rb'\s+', b'', secrets[name])
            secrets[name + ' (unspaced)'] = compact
            secrets[name + ' (spaced)'] = b' '.join(compact[i:i+4] for i in range(0, len(compact), 4))

key_shape = re.compile(rb'sk-[A-Za-z0-9_-]{20,}')
errors = []
with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(f'symlink not permitted: {name}')
        elif path.is_file():
            archive.write(path, name)

with zipfile.ZipFile(staging) as archive:
    names = archive.namelist()
    for item in archive.infolist():
        name = item.filename
        parts = Path(name).parts
        base = Path(name).name
        if any((part.startswith('.env') and part != '.env.example') or part in ('var', 'node_modules') for part in parts) or base.lower().endswith(('.pem', '.db')):
            errors.append(f'forbidden path: {name}')
        data = archive.read(item)
        for label, value in secrets.items():
            if value and value in data:
                errors.append(f'configured secret {label} found in: {name}')
        if key_shape.search(data):
            errors.append(f'key-shaped value found in: {name}')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    raise SystemExit('Scanner FAIL: archive rejected; no new zip retained.')
size = staging.stat().st_size
top = sorted({name.split('/')[0] for name in names})
staging.replace(output)
print('Scanner: PASS')
print(f'Archive: {output}')
print(f'Size: {size:,} bytes ({size / (1024 * 1024):.2f} MiB)')
print(f'Files: {len(names)}')
print('Top level: ' + ', '.join(top))
PY
