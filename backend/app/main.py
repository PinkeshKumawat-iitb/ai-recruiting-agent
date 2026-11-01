from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .routes import router

settings=get_settings()
app=FastAPI(title=settings.app_name,version="0.1.0",description="Recruiting workspace API for jobs, candidates, resumes, interviews, and reports.")
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_url],allow_credentials=True,allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type"])
app.include_router(router)

@app.get("/")
def root(): return {"name":settings.app_name,"docs":"/docs","health":"/api/health"}
