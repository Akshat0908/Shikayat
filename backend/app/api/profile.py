from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlmodel import Session
from ..models import UserProfile

router=APIRouter(prefix="/api/profile")

class ProfileInput(BaseModel):
    name: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=254)

def get_profile(session: Session, default_email: str = "") -> UserProfile:
    return session.get(UserProfile,1) or UserProfile(email=default_email)

@router.get("")
def read_profile(request: Request) -> UserProfile:
    with Session(request.app.state.engine) as session:
        return get_profile(session,request.app.state.config.user_email)

@router.put("")
def save_profile(profile: ProfileInput, request: Request) -> UserProfile:
    with Session(request.app.state.engine) as session:
        record=get_profile(session,request.app.state.config.user_email)
        record.name=profile.name.strip();record.phone=profile.phone.strip();record.email=profile.email.strip()
        session.add(record);session.commit();session.refresh(record);return record
