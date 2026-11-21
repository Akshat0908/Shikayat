"""A labeled sample evaluation, pending the U3 evaluation pipeline."""
from typing import Literal
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix='/api/eval', tags=['evaluation'])
MetricName = Literal['recipient', 'rule', 'deadline', 'reply_classification', 'next_action', 'end_to_end']

class EvaluationSystem(BaseModel):
    metrics: dict[MetricName, bool]
    output: str
    cost_usd: float
    latency_seconds: float

class EvaluationCase(BaseModel):
    id: str
    category: Literal['resolution', 'deflection', 'partial offer', 'wrong-sector trap', 'ambiguous']
    baseline: EvaluationSystem
    shikayat: EvaluationSystem

class EvaluationResult(BaseModel):
    data_source: Literal['sample', 'measured']
    evaluated_at: str | None
    model: str
    case_count: int
    cases: list[EvaluationCase]

METRICS: tuple[MetricName, ...] = ('recipient', 'rule', 'deadline', 'reply_classification', 'next_action', 'end_to_end')
CATEGORIES = ('resolution', 'deflection', 'partial offer', 'wrong-sector trap', 'ambiguous')

@router.get('/latest', response_model=EvaluationResult)
def latest() -> EvaluationResult:
    # Illustrative data only: it is never represented as a measured run.
    cases=[]
    for i in range(20):
        category=CATEGORIES[i % len(CATEGORIES)]
        baseline={name: (i + j) % 4 != 0 for j, name in enumerate(METRICS)}
        shikayat={name: (i + j) % 10 != 0 for j, name in enumerate(METRICS)}
        cases.append(EvaluationCase(
            id=f'SAMPLE-{i+1:02}', category=category,
            baseline=EvaluationSystem(metrics=baseline, output=f'Illustrative baseline output for {category}. Evaluation pending.', cost_usd=0.012, latency_seconds=4.2),
            shikayat=EvaluationSystem(metrics=shikayat, output=f'Illustrative Shikayat output for {category}. Evaluation pending.', cost_usd=0.018, latency_seconds=7.6),
        ))
    return EvaluationResult(data_source='sample', evaluated_at=None, model='Not run', case_count=len(cases), cases=cases)
