from __future__ import annotations
from pathlib import PurePosixPath
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from ..config import get_settings

async def upload_resume(owner_id: str, application_id: str, filename: str, content_type: str, data: bytes) -> str:
    settings=get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503,detail="Supabase Storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.")
    safe_name=PurePosixPath(filename.replace("\\","/")).name.replace(" ","_")
    path=f"{owner_id}/{application_id}/{safe_name}"
    url=f"{settings.supabase_url.rstrip('/')}/storage/v1/object/resumes/{quote(path,safe='/')}"
    headers={"apikey":settings.supabase_service_role_key,"Authorization":f"Bearer {settings.supabase_service_role_key}","Content-Type":content_type,"x-upsert":"true"}
    try:
        async with httpx.AsyncClient(timeout=60) as client: response=await client.post(url,headers=headers,content=data)
    except httpx.HTTPError as exc: raise HTTPException(status_code=502,detail="Supabase Storage could not be reached.") from exc
    if response.is_error: raise HTTPException(status_code=502,detail=f"Supabase Storage returned HTTP {response.status_code} while saving the resume.")
    return path
