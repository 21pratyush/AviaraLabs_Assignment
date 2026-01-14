from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.services.ingest_service import ingest_documents

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("")
def ingest(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    try:        
        document_ids = ingest_documents(db, files)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    
    return {
        "document_ids": document_ids,
        "count": len(document_ids)
    }
