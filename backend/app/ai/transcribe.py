import time
from pathlib import Path
from openai import AsyncOpenAI
from .client import guard, record, cache_key
from ..config import ROOT
from ..config import get_settings

async def transcribe(path: Path) -> str:
    config=get_settings()
    prompt="Hindi aur English Hinglish audio. Roman script mein likho. Preserve order IDs, amounts and ticket numbers exactly."
    import hashlib
    key=cache_key(config.transcribe_model,prompt,hashlib.sha256(path.read_bytes()).hexdigest())
    cache=ROOT/"var"/"llm_cache"/f"audio-{key}.txt"
    if cache.exists():
        record("transcribe",config.transcribe_model,0,0,0,True)
        return cache.read_text()
    guard(config.transcribe_model)
    started=time.monotonic()
    async with AsyncOpenAI(api_key=config.openai_api_key.get_secret_value(),timeout=30,max_retries=2) as client:
        with path.open('rb') as audio:
            response=await client.audio.transcriptions.create(model=config.transcribe_model,file=audio,languages=['hi','en'],prompt=prompt,response_format='json')
    usage=getattr(response,'usage',None)
    record('transcribe',config.transcribe_model,getattr(usage,'input_tokens',0),getattr(usage,'output_tokens',0),(time.monotonic()-started)*1000,False)
    cache.parent.mkdir(parents=True,exist_ok=True)
    cache.write_text(response.text)
    return response.text
