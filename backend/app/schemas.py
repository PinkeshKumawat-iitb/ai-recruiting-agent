from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    role: str = Field(pattern="^(recruiter|candidate)$")
    phone: Optional[str] = Field(default=None, max_length=40)
class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; email: EmailStr; full_name: str; role: str; phone: Optional[str] = None
class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    department: str = Field(default="", max_length=100)
    location: str = Field(default="Remote", max_length=140)
    employment_type: str = Field(default="Full-time", max_length=40)
    description: str = Field(min_length=20, max_length=20000)
    requirements: list[str] = Field(default_factory=list, max_length=30)
    status: str = Field(default="published", pattern="^(draft|published|closed)$")
class JobOut(JobIn):
    model_config = ConfigDict(from_attributes=True)
    id: str; recruiter_id: str; created_at: datetime; applicant_count: int = 0
class ApplyIn(BaseModel):
    cover_note: Optional[str] = Field(default=None, max_length=3000)
class StageIn(BaseModel):
    status: str = Field(pattern="^(applied|screening|interview|offer|rejected)$")
class ScheduleIn(BaseModel):
    scheduled_at: datetime
    language: str = Field(default="en-IN", pattern="^(en-IN|hi-IN)$")
class TurnIn(BaseModel):
    text: Optional[str] = Field(default=None, max_length=4000)
class InterviewOut(BaseModel):
    id: str; application_id: str; candidate_name: str; job_title: str; scheduled_at: Optional[datetime]; language: str; status: str
class TurnOut(BaseModel):
    speaker: str; content: str; language_code: Optional[str]; created_at: datetime
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str; title: str; body: str; link: Optional[str]; read: bool; created_at: datetime
