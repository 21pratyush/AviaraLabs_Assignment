import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from sqlalchemy.orm import Session

from app.db.models import WebhookJob

logger = logging.getLogger(__name__)


def emit_webhook(callback_url: str, payload: Dict[str, Any], retries: int = 2) -> Dict:
    """Simple one-off POST with a fixed retry count. Kept for compatibility."""
    if not callback_url:
        return {"status": "skipped", "reason": "no callback_url"}

    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload)

    for attempt in range(1, retries + 2):
        try:
            resp = requests.post(callback_url, data=body, headers=headers, timeout=10)
            logger.info(f"Webhook POST to {callback_url} status={resp.status_code}")
            return {"status": "sent", "http_status": resp.status_code, "text": resp.text}
        except Exception as e:
            logger.warning(f"Webhook attempt {attempt} failed: {e}")
            time.sleep(1 * attempt)
    return {"status": "failed", "reason": "all attempts failed"}


def schedule_webhook_job(db: Session, callback_url: str, payload: Dict[str, Any], max_attempts: int = 3) -> int:
    """Create a persistent webhook job and return its id."""
    job = WebhookJob(
        callback_url=callback_url,
        payload=payload,
        status="pending",
        attempts=0,
        max_attempts=max_attempts,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def process_webhook_job(db: Session, job_id: int) -> Dict[str, Any]:
    """Process the webhook job with retries and exponential backoff, updating DB state."""
    job: Optional[WebhookJob] = db.get(WebhookJob, job_id)
    if not job:
        return {"status": "error", "reason": "job not found"}

    if not job.callback_url:
        job.status = "skipped"
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
        return {"status": "skipped", "reason": "no callback_url"}

    headers = {"Content-Type": "application/json"}
    body = json.dumps(job.payload or {})

    attempt = job.attempts or 0
    max_attempts = job.max_attempts or 3
    backoff_base = 1

    while attempt < max_attempts:
        attempt += 1
        try:
            resp = requests.post(job.callback_url, data=body, headers=headers, timeout=10)
            job.attempts = attempt
            job.last_response = f"{resp.status_code}:{resp.text}"
            job.updated_at = datetime.utcnow()
            if 200 <= resp.status_code < 300:
                job.status = "succeeded"
                db.add(job)
                db.commit()
                return {"status": "succeeded", "http_status": resp.status_code}
            else:
                logger.warning(f"Webhook job {job_id} responded {resp.status_code}")
        except Exception as e:
            job.attempts = attempt
            job.last_response = str(e)
            job.updated_at = datetime.utcnow()
            logger.warning(f"Webhook job {job_id} attempt {attempt} failed: {e}")

        db.add(job)
        db.commit()

        # exponential backoff
        sleep_for = backoff_base * (2 ** (attempt - 1))
        time.sleep(sleep_for)

    job.status = "failed"
    job.updated_at = datetime.utcnow()
    db.add(job)
    db.commit()
    return {"status": "failed", "attempts": attempt, "last_response": job.last_response}
