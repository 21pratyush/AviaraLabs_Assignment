from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.db.session import get_db
from app.db.vector_db import get_qdrant_client
from app.db.models import Document, DocumentChunk, Extraction, AuditFinding
from app.core.config import COLLECTION_NAME

router = APIRouter(prefix="/admin", tags=["System Admin"])

@router.get("/healthz")
def health_check(db: Session = Depends(get_db)):
    """
    Deep health check: Verifies SQLite and Qdrant connectivity.
    """
    health_status = {
        "status": "healthy",
        "database": "reachable",
        "qdrant": "reachable"
    }
    
    # 1. Check SQLite
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["database"] = f"unreachable: {str(e)}"
        health_status["status"] = "unhealthy"

    # 2. Check Qdrant
    try:
        q_client = get_qdrant_client()
        q_client.get_collections()
    except Exception as e:
        health_status["qdrant"] = f"unreachable: {str(e)}"
        health_status["status"] = "unhealthy"

    if health_status["status"] != "healthy":
        raise HTTPException(status_code=503, detail=health_status)
        
    return health_status


@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db)):
    """
    Returns pipeline statistics for the dashboard.
    """
    # SQL Aggregations
    doc_count = db.query(Document).count()
    chunk_count = db.query(DocumentChunk).count()
    extraction_count = db.query(Extraction).count()
    
    # Severity breakdown for audits
    severity_stats = db.query(
        AuditFinding.severity, func.count(AuditFinding.id)
    ).group_by(AuditFinding.severity).all()
    
    # Qdrant Stats
    q_client = get_qdrant_client()
    try:
        collection_info = q_client.get_collection(COLLECTION_NAME)
        vectors_count = collection_info.vectors_count
    except Exception:
        vectors_count = 0

    return {
        "documents": {
            "total": doc_count,
            "processed_chunks": chunk_count,
            "extractions_completed": extraction_count
        },
        "vector_store": {
            "collection_name": COLLECTION_NAME,
            "total_vectors": vectors_count
        },
        "audit_summary": {sev: count for sev, count in severity_stats},
        "system_timestamp": db.query(func.now()).scalar()
    }