#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
git archive HEAD | tar -xf - -C "$tmp_dir"
# Optional untracked presentation artifacts are included verbatim.
for item in deck VIDEO.md; do
  if [[ -e "$item" && ! -e "$tmp_dir/$item" ]]; then cp -R "$item" "$tmp_dir/$item"; fi
done
python3 - "$tmp_dir" <<'PY'
import os,re,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1]); out=Path.cwd()/'Shikayat-submission.zip'
errors=[]
password=re.compile(rb'(?i)(?:gmail[^\n]{0,40}app[^\n]{0,20}password|app_password)[^\n]{0,20}[=:]\s*["\']?[a-z]{16}(?:["\'\s]|$)|(?<![a-z])(?:[a-z]{4} ){3}[a-z]{4}(?![a-z])')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        if not path.is_file(): continue
        name=path.relative_to(root).as_posix(); parts=Path(name).parts
        if path.name=='.env' or path.suffix.lower() in ('.pem','.db') or 'var' in parts or 'node_modules' in parts:
            errors.append(f'forbidden path: {name}');continue
        data=path.read_bytes()
        if (b's'+b'k-') in data: errors.append(f'forbidden API-key prefix: {name}')
        if password.search(data): errors.append(f'possible Gmail app password: {name}')
        archive.writestr(name,data)
if errors:
    out.unlink(missing_ok=True)
    print('\n'.join(errors),file=sys.stderr)
    raise SystemExit('Submission archive rejected; no zip retained.')
print(f'Created {out}')
PY
