import os
import uuid
from sqlalchemy.orm import Session
from typing import List,Dict
from app.db.models import Document, Extraction, DocumentChunk
from app.db.utils import log_error
from app.core.config import UPLOAD_DIR

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def ingest_documents(db: Session, files: list) -> List[int]:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    document_ids = []

    for file in files:
        # Validate PDF
        if file.content_type not in ("application/pdf", "application/x-pdf"):
            raise ValueError(f"Unsupported file type: {file.content_type}")

        # Generate unique filename
        filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        # Save to disk
        file_bytes = file.file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file.filename}")
        file.file.seek(0)  # reset pointer
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Save metadata to DB
        doc = Document(
            filename=file.filename,
            content_type=file.content_type,
            file_path=file_path
        )
        db.add(doc)
        db.flush()
        document_ids.append(doc.id)

    db.commit()
    return document_ids

def save_document_chunks(
    db: Session,
    document_id: int,
    chunks_data: List[Dict]
) -> List[int]:
    """
    Save document chunks with vector IDs to the database -> Table: DocumentChunk
    
    Args:
        db: Database session
        document_id: ID of the document
        chunks_data: List of dicts with 'text' and 'vector_id' keys
        
    Returns:
        List of created chunk IDs
    """
    chunk_ids = []
    
    try:
        for idx, chunk_data in enumerate(chunks_data):
            chunk = DocumentChunk(
                document_id=document_id,
                chunk_text=chunk_data["text"],
                page_number=chunk_data.get("page_number", 0),
                char_start=chunk_data.get("char_start"),
                char_end=chunk_data.get("char_end"),
                vector_id=str(chunk_data["vector_id"])
            )
            db.add(chunk)

        # Commit all at once
        db.commit()

        # Collect the IDs of newly added chunks
        new_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.id.desc()).limit(len(chunks_data)).all()

        chunk_ids = [chunk.id for chunk in reversed(new_chunks)]

    except Exception as e:
        db.rollback()
        log_error(db, document_id, "document_processing", e)
        raise Exception(f"Failed to save chunks: {str(e)}")
    
    return chunk_ids

def save_extraction_result(
    db: Session,
    document_id: int,
    extracted_json: Dict,
    model_used: str = "gemini-2.5-flash"
) -> Extraction:
    """
    Save extracted contract data to the database -> Table: Extraction
    
    Args:
        db: Database session
        document_id: ID of the document
        extracted_json: Extracted contract data as JSON
        model_used: Name of the model used for extraction
        
    Returns:
        Extraction: The created extraction record
    """
    extraction = Extraction(
        document_id=document_id,
        extracted_json=extracted_json,
        model_used=model_used
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)
    return extraction

def get_document_by_id(db: Session, doc_id: int):
    """Business logic to fetch document status."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        return None
        
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "processing_stage": doc.processing_stage,
        "created_at": doc.created_at
    }

def get_extraction_by_doc_id(db: Session, doc_id: int):
    """Business logic to fetch AI extraction data."""
    return db.query(Extraction).filter(Extraction.document_id == doc_id).first()