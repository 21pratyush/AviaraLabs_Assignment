from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from app.db.session import get_db
from app.db.vector_db import get_qdrant_client
from app.db.models import Document, DocumentChunk, Extraction, AuditFinding, WebhookJob, ErrorLog
from app.core.config import COLLECTION_NAME
import logging

router = APIRouter(prefix="/admin", tags=["System Admin"])
logger = logging.getLogger(__name__)

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
    Aggregates metrics across SQL and Vector databases to provide a 
    holistic view of the system's performance and data state.
    """
    # 1. Pipeline Throughput (SQL)
    # Track how many documents are at which stage of the lifecycle
    doc_status = db.query(Document.status, func.count(Document.id)).group_by(Document.status).all()
    doc_stages = db.query(Document.processing_stage, func.count(Document.id)).group_by(Document.processing_stage).all()
    # This represents the internal relational mapping of text segments
    total_sql_chunks = db.query(DocumentChunk).count()
    avg_chunks_per_doc = db.query(func.avg(
        db.query(func.count(DocumentChunk.id))
        .filter(DocumentChunk.document_id == Document.id)
        .correlate(Document)
        .as_scalar()
    )).scalar() or 0
    
    # 2. Functional Metrics (Extractions & Audits)
    # Measures the value-add: How much data has been successfully structured?
    extraction_count = db.query(Extraction).count()
    audit_severity = db.query(AuditFinding.severity, func.count(AuditFinding.id)).group_by(AuditFinding.severity).all()
    
    # 3. System Reliability (Webhooks & Errors)
    # Measures operational health and identifying bottlenecks/api failures
    webhook_status = db.query(WebhookJob.status, func.count(WebhookJob.id)).group_by(WebhookJob.status).all()
    error_count = db.query(ErrorLog).count()

    # 4. Vector Intelligence (Qdrant Points)
    # Points represent the 'Knowledge Base' size in the RAG system
    q_client = get_qdrant_client()
    points_count = 0
    try:
        info = q_client.get_collection(COLLECTION_NAME)
        # In Qdrant, points_count is the actual number of vector entries
        points_count = info.points_count
    except Exception as e:
        logger.error(f"Qdrant metric fetch failed: {e}")

    return {
        "pipeline": {
            "documents_by_status": {s: c for s, c in doc_status},
            "documents_by_stage": {st: c for st, c in doc_stages},
            "total_extractions": extraction_count
        },
        "content_density": {
            "total_sql_chunks": total_sql_chunks,
            "total_vector_points": points_count,
            "avg_chunks_per_document": round(float(avg_chunks_per_doc), 2),
            "total_ai_extractions": extraction_count
        },
        "analysis": {
            "audit_findings_by_severity": {sev: c for sev, c in audit_severity}
        },
        "operations": {
            "webhook_jobs_by_status": {ws: c for ws, c in webhook_status},
            "total_logged_errors": error_count
        },
        "vector_db": {
            "collection": COLLECTION_NAME,
            "total_points": points_count  # Showing total vectorized chunks
        },
        "system_timestamp": datetime.utcnow()
    }