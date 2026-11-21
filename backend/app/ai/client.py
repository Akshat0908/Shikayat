"""Responses Structured Outputs; credentials and model names come only from settings.

SDK/API reference: https://developers.openai.com/api/docs/guides/structured-outputs
Rates are explicitly configured USD / million tokens, never guessed from model names.
"""
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import TypeVar
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select
from ..config import ROOT, get_settings
from ..db import build_engine, init_db
from ..models import LlmCall

T = TypeVar('T', bound=BaseModel)
_lock = asyncio.Lock()

def cache_key(model: str, instructions: str, inputs: object) -> str:
    return hashlib.sha256(json.dumps([model,instructions,inputs],sort_keys=True).encode()).hexdigest()

def record(task: str, model: str, inputs: int, outputs: int, latency: float, cached: bool) -> None:
    config=get_settings()
    rates=json.loads(config.model_rates_json)
    rate=rates.get(model)
    if rate is None and not cached:
        raise ValueError('Configure MODEL_RATES_JSON for this model before making paid calls')
    cost=0 if cached else (inputs*rate['input']+outputs*rate['output'])/1_000_000
    engine=build_engine(config.database_url)
    init_db(engine)
    try:
        with Session(engine) as session:
            session.add(LlmCall(task=task,model=model,input_tokens=inputs,output_tokens=outputs,est_cost_usd=cost,latency_ms=latency,cached=cached))
            session.commit()
    finally:
        engine.dispose()

def guard(model: str) -> None:
    config=get_settings()
    if model not in json.loads(config.model_rates_json):
        raise ValueError('Configure MODEL_RATES_JSON with verified input/output USD per million tokens')
    engine=build_engine(config.database_url)
    init_db(engine)
    try:
        with Session(engine) as session:
            spent=session.exec(select(func.coalesce(func.sum(LlmCall.est_cost_usd),0))).one()
            if spent >= config.budget_usd:
                raise ValueError('API budget exhausted')
    finally:
        engine.dispose()

async def call_structured(task: str, model: str, schema: type[T], instructions: str, text: str, images: list[str] | None = None) -> T:
    inputs={'text':text,'images':images or [],'schema':schema.model_json_schema()}
    key=cache_key(model,instructions,inputs)
    path=ROOT/'var'/'llm_cache'/f'{key}.json'
    async with _lock:
        started=time.monotonic()
        if path.exists():
            result=schema.model_validate_json(path.read_text())
            record(task,model,0,0,(time.monotonic()-started)*1000,True)
            return result
        config=get_settings()
        if not model or not config.openai_api_key.get_secret_value():
            raise ValueError('Configure OPENAI_API_KEY and the requested model in .env')
        guard(model)
        content=[{'type':'input_text','text':text}]+[{'type':'input_image','image_url':image,'detail':'auto'} for image in images or []]
        async with AsyncOpenAI(api_key=config.openai_api_key.get_secret_value(),timeout=30,max_retries=2) as client:
            response=await client.responses.parse(model=model,instructions=instructions,input=[{'role':'user','content':content}],text_format=schema,store=False)
        usage=response.usage
        record(task,model,usage.input_tokens if usage else 0,usage.output_tokens if usage else 0,(time.monotonic()-started)*1000,False)
        if response.output_parsed is None:
            raise ValueError('Model refused or returned no structured result')
        result=response.output_parsed
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp')
        temporary.write_text(result.model_dump_json())
        temporary.replace(path)
        return result
