import logging
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.services.extraction_service import process_document_embeddings
from app.services.webhook_service import emit_webhook, process_webhook_job
from app.db.models import WebhookJob

logger = logging.getLogger(__name__)


def process_document_pipeline(db: Session, document_ids: List[int], callback_url: str | None = None, webhook_job_id: int | None = None):
    """Modular background pipeline.

    By default this runs the embeddings/QA pipeline (phase-3). Phase 1/2
    extraction are expensive and are performed inside the embedding step
    when needed; we don't call them separately here to reduce churn.
    """
    try:
        logger.info(f"Pipeline start for documents: {document_ids}")

        # Run embeddings creation (this function internally extracts text)
        result = process_document_embeddings(db, document_ids)
        logger.info("Embeddings pipeline completed")

        # Prepare webhook payload
        if callback_url:
            payload = {
                "status": "completed",
                "document_ids": document_ids,
                "results": result
            }

            # If a persistent job id was created, update and process it
            if webhook_job_id:
                try:
                    job = db.get(WebhookJob, webhook_job_id)
                    if job:
                        job.payload = payload
                        job.status = "ready"
                        job.updated_at = datetime.utcnow()
                        db.add(job)
                        db.commit()
                except Exception:
                    logger.exception("Failed to update webhook job payload")

                try:
                    process_webhook_job(db, webhook_job_id)
                except Exception:
                    logger.exception("Failed to process webhook job")
            else:
                try:
                    emit_webhook(callback_url, payload)
                except Exception:
                    logger.exception("One-shot webhook emit failed")

        return {"status": "ok"}

    except Exception:
        logger.exception("Pipeline failed")
        return {"status": "error"}
