from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import WebhookJob

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.get("/jobs/{job_id}")
def get_webhook_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(WebhookJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job.id,
        "callback_url": job.callback_url,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_response": job.last_response,
        "payload": job.payload,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
