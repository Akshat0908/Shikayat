import time
from pathlib import Path
from openai import AsyncOpenAI
from .client import guard, record
from ..config import get_settings

async def transcribe(path: Path) -> str:
    config=get_settings()
    guard(config.transcribe_model)
    started=time.monotonic()
    async with AsyncOpenAI(api_key=config.openai_api_key.get_secret_value(),timeout=30,max_retries=2) as client:
        with path.open('rb') as audio:
            response=await client.audio.transcriptions.create(model=config.transcribe_model,file=audio,languages=['hi','en'],prompt='Hindi aur English Hinglish audio. Roman script mein likho. Preserve order IDs, amounts and ticket numbers exactly.',response_format='json')
    usage=getattr(response,'usage',None)
    record('transcribe',config.transcribe_model,getattr(usage,'input_tokens',0),getattr(usage,'output_tokens',0),(time.monotonic()-started)*1000,False)
    return response.text
