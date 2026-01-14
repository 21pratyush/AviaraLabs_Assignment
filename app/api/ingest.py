from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import logging

from app.db.session import get_db
from app.services.ingest_service import ingest_documents
from app.services.extraction_service import (
    extract_documents_raw_text,
    extract_contract_data,
    process_document_embeddings
)

router = APIRouter(prefix="/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)


def process_document_pipeline(db: Session, document_ids: List[int]):
    """
    Background task to process documents through all extraction phases.
    
    Phase 1: Extract raw text
    Phase 2: Extract contract data
    Phase 3: Create embeddings and store in vector DB
    """
    try:
        logger.info(f"Starting document processing pipeline for IDs: {document_ids}")
        
        # Phase 1: Extract raw text
        logger.info(f"Phase 1: Extracting raw text...")
        phase1_results = extract_documents_raw_text(db, document_ids)
        logger.info(f"Phase 1 completed: {len([r for r in phase1_results.values() if 'error' not in r])} documents extracted")
        
        # Phase 2: Extract contract data with Gemini
        logger.info(f"Phase 2: Extracting contract data with Gemini...")
        phase2_results = extract_contract_data(db, document_ids)
        logger.info(f"Phase 2 completed: {len([r for r in phase2_results.values() if r.get('status') == 'success'])} documents extracted")
        
        # Phase 3: Create embeddings and store in Qdrant
        logger.info(f"Phase 3: Creating embeddings and storing in vector DB...")
        phase3_results = process_document_embeddings(db, document_ids)
        logger.info(f"Phase 3 completed: {len([r for r in phase3_results.values() if r.get('status') == 'success'])} documents embedded")
        
        logger.info(f"Document processing pipeline completed successfully")
        
    except Exception as e:
        logger.error(f"Error in document processing pipeline: {str(e)}", exc_info=True)


@router.post("")
def ingest(
    files: List[UploadFile] = File(...),
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
        
        # Add background task to process documents
        background_tasks.add_task(process_document_pipeline, db, document_ids)
        
        return {
            "status": "ingested",
            "document_ids": document_ids,
            "count": len(document_ids),
            "message": "Documents uploaded successfully. Processing in background..."
        }
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Ingest error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingest failed: {str(e)}")
