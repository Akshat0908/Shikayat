"""Passcode-gated owner sessions for direct sending and sandbox controls."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api/admin')
COOKIE='shikayat_admin'
TTL=8*60*60
_attempts: dict[str,deque[float]]=defaultdict(deque)
_sessions: dict[str,tuple[float,str]]={}

class Login(BaseModel):
    passcode: str = Field(max_length=256)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def is_admin(request: Request) -> bool:
    secret=request.app.state.config.admin_passcode.get_secret_value()
    token=request.cookies.get(COOKIE,'')
    if not secret or not token: return False
    key=digest(token);session=_sessions.get(key)
    if not session: return False
    expires,fingerprint=session
    if time.time()>=expires or not hmac.compare_digest(fingerprint,digest(secret)):
        _sessions.pop(key,None);return False
    return True


def require_admin(request: Request) -> None:
    if not is_admin(request): raise HTTPException(403,'Owner sign-in required')


@router.get('/session')
def session(request: Request,response: Response) -> dict:
    response.headers['Cache-Control']='no-store'
    return {'admin':is_admin(request),'configured':bool(request.app.state.config.admin_passcode.get_secret_value())}


@router.post('/login')
def login(data: Login, request: Request, response: Response) -> dict:
    key=request.client.host if request.client else 'unknown';now=time.time();attempts=_attempts[key]
    while attempts and now-attempts[0]>60: attempts.popleft()
    if len(attempts)>=6: raise HTTPException(429,'Too many attempts; try again in a minute')
    secret=request.app.state.config.admin_passcode.get_secret_value()
    if not secret: raise HTTPException(503,'Owner passcode is not configured')
    if not hmac.compare_digest(data.passcode.encode(),secret.encode()):
        attempts.append(now);raise HTTPException(403,'Incorrect passcode')
    attempts.clear()
    for existing,(expires,_) in list(_sessions.items()):
        if expires<=now: _sessions.pop(existing,None)
    token=secrets.token_urlsafe(32);_sessions[digest(token)]=(now+TTL,digest(secret))
    response.set_cookie(COOKIE,token,max_age=TTL,httponly=True,secure=request.url.scheme=='https',samesite='strict',path='/')
    response.headers['Cache-Control']='no-store'
    return {'admin':True}


@router.post('/logout')
def logout(request: Request,response: Response) -> dict:
    token=request.cookies.get(COOKIE,'')
    if token: _sessions.pop(digest(token),None)
    response.delete_cookie(COOKIE,path='/');response.headers['Cache-Control']='no-store'
    return {'admin':False}
