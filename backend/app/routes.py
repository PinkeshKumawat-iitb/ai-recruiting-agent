from __future__ import annotations
from typing import Optional, Tuple
import base64
import io
from datetime import datetime, timezone
from pathlib import PurePosixPath
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import CurrentUser, get_current_user, require_role
from .config import get_settings
from .database import get_db
from .models import Application, Interview, InterviewTurn, Job, Notification, Profile
from .schemas import ApplyIn, JobIn, JobOut, NotificationOut, ProfileIn, ProfileOut, ScheduleIn, StageIn, TurnIn
from .services import sarvam
from .services.notifications import create_notification, queue_email
from .services.storage import upload_resume

router=APIRouter(prefix="/api")

def _job_out(db:Session, job:Job)->dict:
    count=db.scalar(select(func.count(Application.id)).where(Application.job_id==job.id)) or 0
    return {"id":job.id,"recruiter_id":job.recruiter_id,"title":job.title,"department":job.department,"location":job.location,"employment_type":job.employment_type,"description":job.description,"requirements":job.requirements or [],"status":job.status,"created_at":job.created_at,"applicant_count":count}

def _owned_application(db:Session, application_id:str, recruiter_id:Optional[str]=None, candidate_id:Optional[str]=None)->tuple[Application,Job,Profile]:
    q=select(Application,Job,Profile).join(Job,Job.id==Application.job_id).join(Profile,Profile.id==Application.candidate_id).where(Application.id==application_id)
    if recruiter_id: q=q.where(Job.recruiter_id==recruiter_id)
    if candidate_id: q=q.where(Application.candidate_id==candidate_id)
    row=db.execute(q).first()
    if not row: raise HTTPException(status_code=404,detail="Application not found.")
    return row

def _owned_interview(db:Session, interview_id:str, user:CurrentUser)->tuple[Interview,Application,Job,Profile]:
    q=select(Interview,Application,Job,Profile).join(Application,Application.id==Interview.application_id).join(Job,Job.id==Application.job_id).join(Profile,Profile.id==Application.candidate_id).where(Interview.id==interview_id)
    if user.role=="candidate": q=q.where(Profile.id==user.id)
    elif user.role=="recruiter": q=q.where(Job.recruiter_id==user.id)
    row=db.execute(q).first()
    if not row: raise HTTPException(status_code=404,detail="Interview not found.")
    return row

@router.get("/health")
def health():
    s=get_settings()
    return {"status":"ok","service":"AI Recruiting Agent API","configured":{"database":bool(s.database_url),"supabase_auth":bool(s.supabase_url and s.public_key),"resume_storage":bool(s.supabase_url and s.supabase_service_role_key),"sarvam":bool(s.sarvam_api_key),"email":bool(s.smtp_host and s.smtp_user and s.smtp_password and s.smtp_from)}}

@router.get("/profile",response_model=ProfileOut)
def get_profile(user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    profile=db.get(Profile,user.id)
    if not profile: raise HTTPException(status_code=404,detail="Profile not found.")
    return profile

@router.put("/profile",response_model=ProfileOut)
def update_profile(payload:ProfileIn,user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    if payload.role!=user.role: raise HTTPException(status_code=403,detail="Account type cannot be changed here.")
    profile=db.get(Profile,user.id);profile.full_name=payload.full_name.strip();profile.phone=payload.phone
    db.commit();db.refresh(profile);return profile

@router.get("/jobs")
def public_jobs(db:Session=Depends(get_db)):
    jobs=db.scalars(select(Job).where(Job.status=="published").order_by(Job.created_at.desc())).all()
    return [_job_out(db,j) for j in jobs]

@router.get("/jobs/manage")
def my_jobs(user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    jobs=db.scalars(select(Job).where(Job.recruiter_id==user.id).order_by(Job.created_at.desc())).all()
    return [_job_out(db,j) for j in jobs]

@router.post("/jobs",status_code=201)
def create_job(payload:JobIn,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    job=Job(recruiter_id=user.id,**payload.model_dump());db.add(job);db.commit();db.refresh(job);return _job_out(db,job)

@router.patch("/jobs/{job_id}")
def update_job(job_id:str,payload:JobIn,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    job=db.scalar(select(Job).where(Job.id==job_id,Job.recruiter_id==user.id))
    if not job: raise HTTPException(status_code=404,detail="Job not found.")
    for key,value in payload.model_dump().items(): setattr(job,key,value)
    db.commit();db.refresh(job);return _job_out(db,job)

@router.delete("/jobs/{job_id}",status_code=204)
def delete_job(job_id:str,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    job=db.scalar(select(Job).where(Job.id==job_id,Job.recruiter_id==user.id))
    if not job: raise HTTPException(status_code=404,detail="Job not found.")
    db.delete(job);db.commit()

@router.post("/jobs/{job_id}/apply",status_code=201)
def apply_job(job_id:str,payload:ApplyIn,user:CurrentUser=Depends(require_role("candidate")),db:Session=Depends(get_db)):
    job=db.scalar(select(Job).where(Job.id==job_id,Job.status=="published"))
    if not job: raise HTTPException(status_code=404,detail="This job is no longer accepting applications.")
    if db.scalar(select(Application.id).where(Application.job_id==job.id,Application.candidate_id==user.id)):
        raise HTTPException(status_code=409,detail="You have already applied to this role.")
    application=Application(job_id=job.id,candidate_id=user.id);db.add(application)
    try: db.commit()
    except IntegrityError: db.rollback();raise HTTPException(status_code=409,detail="You have already applied to this role.")
    return {"id":application.id,"status":application.status,"job_title":job.title}

@router.get("/applications")
def applications(user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    q=select(Application,Job,Profile).join(Job,Job.id==Application.job_id).join(Profile,Profile.id==Application.candidate_id)
    if user.role=="candidate": q=q.where(Application.candidate_id==user.id)
    else: q=q.where(Job.recruiter_id==user.id)
    rows=db.execute(q.order_by(Application.applied_at.desc())).all()
    return [{"id":a.id,"job_id":j.id,"job_title":j.title,"candidate_id":p.id,"candidate_name":p.full_name,"candidate_email":p.email,"status":a.status,"resume_filename":a.resume_filename,"has_resume":bool(a.resume_path),"screening":a.screening,"applied_at":a.applied_at} for a,j,p in rows]

def _extract_resume(filename:str,data:bytes)->str:
    suffix=PurePosixPath(filename.lower()).suffix
    try:
        if suffix==".pdf":
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(data)); text="\n".join(page.extract_text() or "" for page in reader.pages[:30])
        elif suffix==".docx":
            from docx import Document
            doc=Document(io.BytesIO(data)); text="\n".join(paragraph.text for paragraph in doc.paragraphs)
        else: text=data.decode("utf-8",errors="ignore")
    except Exception as exc: raise HTTPException(status_code=422,detail="We could not read this resume. Please upload a text-based PDF or DOCX.") from exc
    text=text.strip()
    if not text: raise HTTPException(status_code=422,detail="No readable text was found in this resume.")
    return text[:50000]

@router.post("/applications/{application_id}/resume")
async def upload_application_resume(application_id:str,file:UploadFile=File(...),user:CurrentUser=Depends(require_role("candidate")),db:Session=Depends(get_db)):
    application,job,candidate=_owned_application(db,application_id,candidate_id=user.id)
    filename=PurePosixPath((file.filename or "resume.pdf").replace("\\","/")).name
    suffix=PurePosixPath(filename.lower()).suffix
    if suffix not in {".pdf",".docx",".txt"}: raise HTTPException(status_code=415,detail="Upload a PDF, DOCX, or TXT resume.")
    data=await file.read(8*1024*1024+1)
    if len(data)>8*1024*1024: raise HTTPException(status_code=413,detail="Resume files must be 8 MB or smaller.")
    resume_text=_extract_resume(filename,data)
    content_type=file.content_type or ({".pdf":"application/pdf",".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",".txt":"text/plain"}[suffix])
    path=await upload_resume(user.id,application.id,filename,content_type,data)
    application.resume_filename=filename;application.resume_path=path;application.resume_text=resume_text;db.commit()
    return {"message":"Resume uploaded.","filename":filename,"screening_ready":True}

@router.get("/applications/{application_id}/resume-url")
def resume_url(application_id:str,user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    if user.role=="candidate": application,job,candidate=_owned_application(db,application_id,candidate_id=user.id)
    else: application,job,candidate=_owned_application(db,application_id,recruiter_id=user.id)
    if not application.resume_path: raise HTTPException(status_code=404,detail="No resume has been uploaded yet.")
    s=get_settings()
    if not s.supabase_service_role_key: raise HTTPException(status_code=503,detail="Supabase Storage is not configured.")
    import httpx
    path=application.resume_path
    response=httpx.post(f"{s.supabase_url.rstrip('/')}/storage/v1/object/sign/resumes/{path}",headers={"apikey":s.supabase_service_role_key,"Authorization":f"Bearer {s.supabase_service_role_key}","Content-Type":"application/json"},json={"expiresIn":300},timeout=15)
    if response.is_error: raise HTTPException(status_code=502,detail="Could not create a temporary resume link.")
    result=response.json(); signed=result.get("signedURL") or result.get("signedUrl")
    if signed and signed.startswith("/"): signed=s.supabase_url.rstrip("/")+"/storage/v1"+signed
    return {"url":signed,"expires_in":300}

@router.post("/applications/{application_id}/screen")
async def screen_application(application_id:str,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    application,job,candidate=_owned_application(db,application_id,recruiter_id=user.id)
    if not application.resume_text: raise HTTPException(status_code=409,detail="The candidate has not uploaded a readable resume yet.")
    prompt=("You are a recruiting assistant. Compare only job-related evidence. Never infer protected characteristics or use them in scoring. Provide useful, cautious evidence to support a human recruiter. Return JSON with keys: summary (string), overall_score (integer 0-100), recommendation (Advance, Review, or Do not advance), matching_skills (array of strings), gaps_to_clarify (array of strings), evidence (array of strings). Do not make an automatic hiring decision.")
    raw=await sarvam.chat([{"role":"system","content":prompt},{"role":"user","content":f"Role: {job.title}\nDescription: {job.description[:5000]}\nRequirements: {job.requirements}\nResume:\n{application.resume_text[:12000]}"}],json_mode=True,max_tokens=900)
    import json
    try: report=json.loads(raw)
    except json.JSONDecodeError as exc: raise HTTPException(status_code=502,detail="Sarvam returned an unexpected screening report.") from exc
    application.screening=report;application.status="screening";db.commit()
    return report

@router.patch("/applications/{application_id}/stage")
def change_stage(application_id:str,payload:StageIn,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    application,job,candidate=_owned_application(db,application_id,recruiter_id=user.id)
    application.status=payload.status;db.commit()
    create_notification(db,candidate.id,"Application update",f"Your application for {job.title} has moved to: {payload.status}.","/dashboard")
    return {"id":application.id,"status":application.status}

@router.get("/interviews")
def list_interviews(user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    q=select(Interview,Application,Job,Profile).join(Application,Application.id==Interview.application_id).join(Job,Job.id==Application.job_id).join(Profile,Profile.id==Application.candidate_id)
    q=q.where(Profile.id==user.id) if user.role=="candidate" else q.where(Job.recruiter_id==user.id)
    rows=db.execute(q.order_by(Interview.scheduled_at.asc().nullslast())).all()
    return [{"id":i.id,"application_id":a.id,"candidate_name":p.full_name,"job_title":j.title,"scheduled_at":i.scheduled_at,"language":i.language,"status":i.status,"evaluation":i.evaluation if user.role=="recruiter" else None} for i,a,j,p in rows]

@router.post("/applications/{application_id}/interview",status_code=201)
def schedule_interview(application_id:str,payload:ScheduleIn,background:BackgroundTasks,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    application,job,candidate=_owned_application(db,application_id,recruiter_id=user.id)
    if not application.resume_text: raise HTTPException(status_code=409,detail="Ask the candidate to upload a resume before scheduling an interview.")
    if db.scalar(select(Interview.id).where(Interview.application_id==application.id)): raise HTTPException(status_code=409,detail="An interview is already scheduled for this application.")
    interview=Interview(application_id=application.id,scheduled_at=payload.scheduled_at,language=payload.language,status="scheduled")
    application.status="interview";db.add(interview);db.commit();db.refresh(interview)
    when=payload.scheduled_at.astimezone(timezone.utc).strftime("%b %d, %Y at %H:%M UTC")
    title="AI interview scheduled";body=f"Your interview for {job.title} is scheduled for {when}. Sign in to join your interview."
    create_notification(db,candidate.id,title,body,f"/interviews/{interview.id}")
    queue_email(background,candidate.email,title,f"Hello {candidate.full_name},\n\n{body}\n\n{get_settings().frontend_url}/interviews/{interview.id}")
    return {"id":interview.id,"application_id":application.id,"scheduled_at":interview.scheduled_at,"language":interview.language,"status":interview.status}

@router.get("/interviews/{interview_id}")
def interview_detail(interview_id:str,user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    interview,application,job,candidate=_owned_interview(db,interview_id,user)
    turns=db.scalars(select(InterviewTurn).where(InterviewTurn.interview_id==interview.id).order_by(InterviewTurn.created_at)).all()
    return {"id":interview.id,"application_id":application.id,"job_title":job.title,"job_description":job.description,"candidate_name":candidate.full_name,"language":interview.language,"status":interview.status,"scheduled_at":interview.scheduled_at,"turns":[{"speaker":t.speaker,"content":t.content,"language_code":t.language_code,"created_at":t.created_at} for t in turns]}

@router.post("/interviews/{interview_id}/start")
async def start_interview(interview_id:str,user:CurrentUser=Depends(require_role("candidate")),db:Session=Depends(get_db)):
    interview,application,job,candidate=_owned_interview(db,interview_id,user)
    if interview.status=="completed": raise HTTPException(status_code=409,detail="This interview is already complete.")
    interview.status="in_progress";interview.started_at=interview.started_at or datetime.now(timezone.utc);db.commit()
    existing=db.scalars(select(InterviewTurn).where(InterviewTurn.interview_id==interview.id).order_by(InterviewTurn.created_at)).all()
    if existing:
        last=existing[-1]
        if last.speaker=="interviewer":
            audio=await sarvam.speak(last.content,interview.language)
            return {"started":True,"already_started":True,"reply":last.content,"audio_base64":base64.b64encode(audio).decode("ascii"),"audio_type":"audio/wav"}
        return {"started":True,"already_started":True}
    intro=(f"Namaste {candidate.full_name}. Main aaj {job.title} role ke liye aapka interview loonga. Aap Hindi ya English mein jawab de sakte hain. Kya aap shuru karne ke liye taiyaar hain?" if interview.language=="hi-IN" else f"Hello {candidate.full_name}, I will be interviewing you for the {job.title} role today. You may answer in English or Hindi. Are you ready to begin?")
    turn=InterviewTurn(interview_id=interview.id,speaker="interviewer",content=intro,language_code=interview.language);db.add(turn);db.commit()
    audio=await sarvam.speak(intro,interview.language)
    return {"started":True,"reply":intro,"audio_base64":base64.b64encode(audio).decode("ascii"),"audio_type":"audio/wav"}

@router.post("/interviews/{interview_id}/turn")
async def interview_turn(interview_id:str,background:BackgroundTasks,audio:Optional[UploadFile]=File(default=None),text:Optional[str]=Form(default=None),user:CurrentUser=Depends(require_role("candidate")),db:Session=Depends(get_db)):
    interview,application,job,candidate=_owned_interview(db,interview_id,user)
    if interview.status!="in_progress": raise HTTPException(status_code=409,detail="Start the interview before answering.")
    transcript=(text or "").strip();detected=interview.language
    if audio is not None:
        data=await audio.read(10*1024*1024+1)
        if len(data)>10*1024*1024: raise HTTPException(status_code=413,detail="An interview audio turn must be 10 MB or smaller.")
        transcript,detected=await sarvam.transcribe(audio.filename or "answer.webm",data,audio.content_type or "audio/webm",interview.language)
    if not transcript: raise HTTPException(status_code=422,detail="We could not hear a response. Please try again or type your answer.")
    old=db.scalars(select(InterviewTurn).where(InterviewTurn.interview_id==interview.id).order_by(InterviewTurn.created_at)).all()
    candidate_turn=InterviewTurn(interview_id=interview.id,speaker="candidate",content=transcript,language_code=detected);db.add(candidate_turn);db.commit()
    candidate_answers=sum(1 for turn in old if turn.speaker=="candidate")+1
    lang_rule="Respond in Hindi (Devanagari) while accepting English technical terms." if interview.language=="hi-IN" else "Respond in natural, concise English."
    system=(f"You are a respectful, structured AI interviewer for the {job.title} position. Conduct one question at a time; acknowledge briefly, then ask one relevant follow-up. Never ask about protected traits, age, family, health, religion, or other personal topics. Ask for concrete work examples. Keep each response under 55 words. {lang_rule} You have asked {candidate_answers} candidate questions. Ask at most 7 total; after the 7th answer, thank them and say the interview is complete.")
    messages=[{"role":"system","content":system}]
    for turn in old:
        messages.append({"role":"assistant" if turn.speaker=="interviewer" else "user","content":turn.content})
    messages.append({"role":"user","content":transcript})
    reply=await sarvam.chat(messages,max_tokens=160)
    ai_turn=InterviewTurn(interview_id=interview.id,speaker="interviewer",content=reply,language_code=interview.language);db.add(ai_turn);db.commit()
    audio_bytes=await sarvam.speak(reply,interview.language)
    return {"transcript":transcript,"reply":reply,"audio_base64":base64.b64encode(audio_bytes).decode("ascii"),"audio_type":"audio/wav","question_count":candidate_answers,"max_questions":7}

@router.post("/interviews/{interview_id}/finish")
async def finish_interview(interview_id:str,user:CurrentUser=Depends(require_role("candidate")),db:Session=Depends(get_db)):
    interview,application,job,candidate=_owned_interview(db,interview_id,user)
    if interview.status=="completed" and interview.evaluation: return interview.evaluation
    turns=db.scalars(select(InterviewTurn).where(InterviewTurn.interview_id==interview.id).order_by(InterviewTurn.created_at)).all()
    candidate_count=sum(1 for t in turns if t.speaker=="candidate")
    if candidate_count<1: raise HTTPException(status_code=409,detail="Answer at least one interview question before finishing.")
    transcript="\n".join(("Interviewer: " if t.speaker=="interviewer" else "Candidate: ")+t.content for t in turns)
    evaluation=await sarvam.evaluate_interview(job.title,job.description,application.resume_text or "No resume uploaded",transcript,interview.language)
    interview.evaluation=evaluation;interview.status="completed";interview.completed_at=datetime.now(timezone.utc);db.commit()
    notification_title="Interview report is ready"
    create_notification(db,job.recruiter_id,notification_title,f"The interview with {candidate.full_name} for {job.title} has been completed.","/reports")
    return evaluation

@router.get("/interviews/{interview_id}/report")
def interview_report(interview_id:str,user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    interview,application,job,candidate=_owned_interview(db,interview_id,user)
    if interview.status!="completed" or not interview.evaluation: raise HTTPException(status_code=409,detail="The interview report is not ready yet.")
    turns=db.scalars(select(InterviewTurn).where(InterviewTurn.interview_id==interview.id).order_by(InterviewTurn.created_at)).all()
    return {"candidate_name":candidate.full_name,"candidate_email":candidate.email,"job_title":job.title,"language":interview.language,"evaluation":interview.evaluation,"transcript":[{"speaker":t.speaker,"content":t.content,"created_at":t.created_at} for t in turns]}

@router.get("/notifications")
def notifications(user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Notification).where(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [NotificationOut.model_validate(row) for row in rows]

@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id:str,user:CurrentUser=Depends(get_current_user),db:Session=Depends(get_db)):
    item=db.scalar(select(Notification).where(Notification.id==notification_id,Notification.user_id==user.id))
    if not item: raise HTTPException(status_code=404,detail="Notification not found.")
    item.read=True;db.commit();return {"read":True}

@router.get("/dashboard/recruiter")
def recruiter_dashboard(user:CurrentUser=Depends(require_role("recruiter")),db:Session=Depends(get_db)):
    jobs=db.scalars(select(Job).where(Job.recruiter_id==user.id).order_by(Job.created_at.desc())).all()
    job_ids=[j.id for j in jobs]
    apps=db.scalars(select(Application).where(Application.job_id.in_(job_ids)).order_by(Application.applied_at.desc()).limit(12)).all() if job_ids else []
    upcoming=db.execute(select(Interview,Application,Job,Profile).join(Application,Application.id==Interview.application_id).join(Job,Job.id==Application.job_id).join(Profile,Profile.id==Application.candidate_id).where(Job.recruiter_id==user.id,Interview.status!="completed").order_by(Interview.scheduled_at.asc().nullslast()).limit(5)).all()
    return {"counts":{"active_jobs":sum(1 for j in jobs if j.status=="published"),"candidates":db.scalar(select(func.count(func.distinct(Application.candidate_id))).where(Application.job_id.in_(job_ids))) if job_ids else 0,"interviews":db.scalar(select(func.count(Interview.id)).join(Application).join(Job).where(Job.recruiter_id==user.id,Interview.status.in_(["scheduled","in_progress"]))) or 0,"reports":db.scalar(select(func.count(Interview.id)).join(Application).join(Job).where(Job.recruiter_id==user.id,Interview.status=="completed")) or 0},"jobs":[_job_out(db,j) for j in jobs[:5]],"applications":[{"id":a.id,"job_title":j.title,"candidate_name":p.full_name,"candidate_email":p.email,"status":a.status,"resume_filename":a.resume_filename,"screening":a.screening,"applied_at":a.applied_at} for a,j,p in db.execute(select(Application,Job,Profile).join(Job).join(Profile,Profile.id==Application.candidate_id).where(Application.job_id.in_(job_ids)).order_by(Application.applied_at.desc()).limit(8)).all()] if job_ids else [],"upcoming_interviews":[{"id":i.id,"candidate_name":p.full_name,"job_title":j.title,"scheduled_at":i.scheduled_at,"language":i.language,"status":i.status} for i,a,j,p in upcoming]}
