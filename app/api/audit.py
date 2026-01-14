from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit_service import scan_documents_for_risks

router = APIRouter(prefix="/audit", tags=["audit"])


@router.post("")
def audit_documents(document_ids: List[int], db: Session = Depends(get_db)):
    """
    Scan provided documents for risky clauses and return findings with citations.

    Request body: JSON array of document IDs: [1,2]
    """
    if not document_ids or len(document_ids) == 0:
        raise HTTPException(status_code=400, detail="Provide at least one document_id")

    try:
        findings = scan_documents_for_risks(db=db, document_ids=document_ids)
        return {"status": "success", "findings": findings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")