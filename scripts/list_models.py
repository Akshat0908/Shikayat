"""List model IDs without logging credentials or HTTP headers."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openai import AsyncOpenAI
from backend.app.config import get_settings

async def main() -> None:
    config=get_settings()
    key=config.openai_api_key.get_secret_value()
    if not key:
        print('FAIL: OPENAI_API_KEY is missing from .env')
        raise SystemExit(1)
    try:
        async with AsyncOpenAI(api_key=key,timeout=30,max_retries=0) as client:
            models=await client.models.list()
            for id in sorted(model.id for model in models.data): print(id)
    except Exception as error:
        status=getattr(error,'status_code',None)
        body=getattr(error,'body',None)
        code=body.get('code') if isinstance(body,dict) else None
        print(f'FAIL: {type(error).__name__}; status={status}; code={code}')
        raise SystemExit(1)

if __name__=='__main__': asyncio.run(main())
