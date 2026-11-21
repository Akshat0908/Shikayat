from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class FactEvent(BaseModel):
    date: date | None
    what: str

class ContactAttempt(BaseModel):
    date: date | None
    channel: str
    ticket_id: str | None

class FieldConfidence(BaseModel):
    company_name: float
    order_id: float
    amount_inr: float
    purchase_date: float

class FactProvenance(BaseModel):
    field: str
    origin: Literal['screenshot','voice','text','email']
    source_excerpt: str | None
    bbox: list[float] | None

class CaseFacts(BaseModel):
    company_name: str | None
    order_id: str | None
    amount_inr: float | None = Field(ge=0)
    purchase_date: date | None
    issue_type: Literal['refund_not_received','wrong_item','not_delivered','damaged','overcharged','cancellation','service_failure','other']
    issue_summary_en: str
    user_demand: Literal['refund','replacement','delivery','compensation','other']
    events: list[FactEvent]
    contact_attempts: list[ContactAttempt]
    days_elapsed: int | None = Field(ge=0)
    missing_info: list[str]
    field_confidence: FieldConfidence
    provenance: list[FactProvenance] = []
    purchase_channel: Literal['brand_website','brand_app','marketplace','offline','unknown'] = 'unknown'

    @model_validator(mode='after')
    def unknowns(self) -> 'CaseFacts':
        for name in ('company_name','order_id','amount_inr','purchase_date','days_elapsed'):
            if getattr(self,name) is None and name not in self.missing_info:
                self.missing_info.append(name)
        if any(not 0 <= n <= 1 for n in self.field_confidence.model_dump().values()):
            raise ValueError('Confidence must be between zero and one')
        return self

class ShortText(BaseModel):
    text: str
