from __future__ import annotations
from typing import Optional, Tuple
import base64
import json
import httpx
from fastapi import HTTPException
from ..config import get_settings

API_ROOT = "https://api.sarvam.ai"

def _headers() -> dict[str, str]:
    key = get_settings().sarvam_api_key
    if not key:
        raise HTTPException(status_code=503, detail="Sarvam is not configured. Set SARVAM_API_KEY in backend/.env.")
    return {"api-subscription-key": key}

async def transcribe(filename: str, data: bytes, content_type: str, language: str) -> Tuple[str, Optional[str]]:
    headers = _headers()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{API_ROOT}/speech-to-text", headers=headers, data={"model": get_settings().sarvam_stt_model, "mode": "transcribe", "language_code": language}, files={"file": (filename, data, content_type)})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Sarvam speech recognition could not be reached.") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail=f"Sarvam speech recognition returned HTTP {response.status_code}.")
    result=response.json()
    return str(result.get("transcript", "")).strip(), result.get("language_code")

async def speak(text: str, language: str) -> bytes:
    headers = _headers(); headers["Content-Type"]="application/json"
    payload={"model":get_settings().sarvam_tts_model,"text":text[:2400],"language_code":language,"speaker":"shubh_enhi_ads" if language=="en-IN" else "shubh","speech_sample_rate":22050,"output_audio_codec":"wav"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response=await client.post(f"{API_ROOT}/text-to-speech",headers=headers,json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail="Sarvam speech synthesis could not be reached.") from exc
    if response.is_error:
        raise HTTPException(status_code=502,detail=f"Sarvam speech synthesis returned HTTP {response.status_code}.")
    audios=response.json().get("audios") or []
    if not audios:
        raise HTTPException(status_code=502,detail="Sarvam returned no speech audio.")
    try: return base64.b64decode(audios[0])
    except (ValueError, TypeError) as exc: raise HTTPException(status_code=502,detail="Sarvam returned invalid audio data.") from exc

async def chat(messages: list[dict], *, json_mode: bool = False, max_tokens: int = 500) -> str:
    headers=_headers();headers["Content-Type"]="application/json"
    payload={"model":get_settings().sarvam_chat_model,"messages":messages,"temperature":0.35,"max_tokens":max_tokens}
    if json_mode: payload["response_format"]={"type":"json_object"}
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response=await client.post(f"{API_ROOT}/v1/chat/completions",headers=headers,json=payload)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502,detail="Sarvam chat could not be reached.") from exc
    if response.is_error:
        raise HTTPException(status_code=502,detail=f"Sarvam chat returned HTTP {response.status_code}.")
    try: return str(response.json()["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc: raise HTTPException(status_code=502,detail="Sarvam returned an unexpected chat response.") from exc

async def evaluate_interview(job_title: str, description: str, resume: str, transcript: str, language: str) -> dict:
    system=("You are an evidence-based recruiting interviewer. Assess only job-relevant skills and statements in the transcript and resume. Never infer protected characteristics, age, gender, ethnicity, health, religion, family status, or personality. Return valid JSON only with keys: summary (string), recommendation (one of Advance, Review, Do not advance), overall_score (integer 0-100), competencies (array of objects with name, score 0-100, evidence string), strengths (array of strings), follow_up (array of strings). Be fair, concise, and cite evidence. Scores support human review and must not be treated as automatic hiring decisions.")
    user=f"Role: {job_title}\nJob description: {description[:6000]}\nResume text: {resume[:7000]}\nInterview language: {language}\nTranscript:\n{transcript[:14000]}\nAssess this evidence. Return the requested JSON."
    raw=await chat([{"role":"system","content":system},{"role":"user","content":user}],json_mode=True,max_tokens=1200)
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or not isinstance(value.get("competencies"),list): raise ValueError("unexpected report shape")
        return value
    except (json.JSONDecodeError,ValueError) as exc:
        raise HTTPException(status_code=502,detail="Sarvam returned a report in an unexpected format. Please try again.") from exc
