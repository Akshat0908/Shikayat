"""Warm the sample extraction and draft cache via the owner-only endpoint."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from backend.app.config import get_settings


def main() -> None:
    secret=get_settings().admin_passcode.get_secret_value()
    if not secret: raise RuntimeError('Set ADMIN_PASSCODE before warming the cache')
    with httpx.Client(base_url='http://localhost:8000',timeout=120) as client:
        response=client.post('/api/admin/login',json={'passcode':secret});response.raise_for_status()
        response=client.post('/api/demo/warm');response.raise_for_status()
        print('Cache warmed:',response.json()['status'])

if __name__=='__main__':
    main()
