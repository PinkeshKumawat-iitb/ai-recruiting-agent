from __future__ import annotations
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import httpx
from .config import get_settings
from .database import get_db
from .models import Profile

bearer = HTTPBearer(auto_error=False)
@dataclass
class CurrentUser:
    id: str
    email: str
    full_name: str
    role: str

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer), db: Session = Depends(get_db)) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    settings = get_settings()
    key = settings.public_key
    if not settings.supabase_url or not key:
        raise HTTPException(status_code=503, detail="Supabase Auth is not configured. Set its URL and publishable key in backend/.env.")
    try:
        response = httpx.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user", headers={"apikey": key, "Authorization": f"Bearer {credentials.credentials}"}, timeout=10)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Could not reach Supabase Auth.") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    auth_user = response.json()
    user_id = str(auth_user.get("id", "")); email = auth_user.get("email") or ""
    if not user_id or not email:
        raise HTTPException(status_code=401, detail="The Supabase account is missing an email address.")
    profile = db.get(Profile, user_id)
    metadata = auth_user.get("user_metadata") or {}
    if profile is None:
        role = metadata.get("role") if metadata.get("role") in {"recruiter", "candidate"} else "candidate"
        profile = Profile(id=user_id, email=email, full_name=metadata.get("full_name") or email.split("@")[0], role=role)
        db.add(profile); db.commit(); db.refresh(profile)
    return CurrentUser(id=profile.id, email=profile.email, full_name=profile.full_name, role=profile.role)

def require_role(*roles: str):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="This action is not available for your account type.")
        return user
    return dependency
