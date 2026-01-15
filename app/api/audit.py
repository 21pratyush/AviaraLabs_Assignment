from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit_service import scan_documents_for_risks

router = APIRouter(prefix="/analysis", tags=["Contract Analysis"])

@router.post("/audit")
def audit_documents(
    document_ids: List[int], 
    strategy: str = Query("regex", enum=["regex", "ai"], description="Choose audit logic"),
    db: Session = Depends(get_db)
):
    """
    Scan documents for risky clauses.
    
    - **regex**: Fast, rule-based scanning of raw text chunks.
    - **ai**: Intelligent risk reasoning based on structured data in the extraction table.
    """
    if not document_ids:
        raise HTTPException(status_code=400, detail="Provide at least one document_id")

    try:
        results = scan_documents_for_risks(
            db=db, 
            document_ids=document_ids, 
            strategy=strategy
        )
        return {
            "status": "success", 
            "strategy_used": strategy,
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")