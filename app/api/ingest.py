from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Form
from sqlalchemy.orm import Session
from typing import List
import logging

from app.db.session import get_db
from app.services.ingest_service import ingest_documents, get_document_by_id, get_extraction_by_doc_id
from app.services.pipeline_service import process_document_pipeline
from app.services.webhook_service import schedule_webhook_job

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

@router.post("/upload")
def ingest(
    files: List[UploadFile] = File(...),
    callback_url: str | None = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Ingest documents and process them in background.
    
    - Accepts PDF files and stores them
    - Returns document IDs immediately
    - Triggers background processing pipeline:
      * Phase 1: Extract raw text
      * Phase 2: Extract structured data (parties, terms, etc.)
      * Phase 3: Create embeddings and store in vector DB
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    
    try:
        # Store files in DB and disk
        document_ids = ingest_documents(db, files)
        
        # If callback_url provided, schedule a persistent webhook job and pass job_id
        webhook_job_id = None
        if callback_url:
            initial_payload = {"status": "pending", "document_ids": document_ids}
            try:
                webhook_job_id = schedule_webhook_job(db, callback_url, initial_payload)
            except Exception:
                logger.exception("Failed to schedule webhook job; will continue without persistent job")

        # Add background task to process documents; pass callback_url and webhook_job_id if provided
        background_tasks.add_task(process_document_pipeline, db, document_ids, callback_url, webhook_job_id)
        
        response = {
            "status": "ingested",
            "document_ids": document_ids,
            "count": len(document_ids),
            "message": "Documents uploaded successfully. Processing in background..."
        }
        if webhook_job_id:
            response["webhook_job_id"] = webhook_job_id
        return response
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Ingest error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingest failed: {str(e)}")

@router.get("/{doc_id}")
def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    # The API just asks the service for data
    doc_data = get_document_by_id(db, doc_id)
    
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return doc_data

@router.get("/{doc_id}/extraction")
def get_document_extraction(doc_id: int, db: Session = Depends(get_db)):
    extraction = get_extraction_by_doc_id(db, doc_id)
    
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not ready or not found")
    
    return extraction