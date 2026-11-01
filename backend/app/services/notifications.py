from __future__ import annotations
from typing import Optional, Tuple
import smtplib
from email.message import EmailMessage
from fastapi import BackgroundTasks
from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import Notification

def create_notification(db: Session, user_id: str, title: str, body: str, link: Optional[str] = None) -> Notification:
    item=Notification(user_id=user_id,title=title,body=body,link=link)
    db.add(item); db.commit(); db.refresh(item)
    return item

def _send_email(to: str, subject: str, body: str) -> None:
    settings=get_settings()
    if not all([settings.smtp_host,settings.smtp_user,settings.smtp_password,settings.smtp_from]): return
    message=EmailMessage();message["Subject"]=subject;message["From"]=settings.smtp_from;message["To"]=to;message.set_content(body)
    with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=15) as server:
        server.starttls();server.login(settings.smtp_user,settings.smtp_password);server.send_message(message)

def queue_email(background: BackgroundTasks, to: str, subject: str, body: str) -> None:
    settings=get_settings()
    if all([settings.smtp_host,settings.smtp_user,settings.smtp_password,settings.smtp_from]): background.add_task(_send_email,to,subject,body)
