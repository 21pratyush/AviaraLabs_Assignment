from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.retrieval_service import rag_query_stream, rag_query

router = APIRouter(tags=["RAG & Query"])

@router.get("/ask/stream")
def rag_search_query_stream(
    query: str = Query(..., min_length=1, description="Query to answer"),
    document_id: list[int] = Query(..., description="Document ID(s) to query within"),
    limit: int = Query(5, ge=1, le=20, description="Number of chunks to retrieve"),
    score_threshold: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity score"),
    db: Session = Depends(get_db)
):
    """
    RAG Query with Streaming within specific document(s): Search and stream AI answer.
    
    - Filters to only the specified document_id(s)
    - Retrieves relevant chunks using semantic search
    - Sends chunks to Gemini with system prompt
    - Streams answer chunks in real-time as JSON-L format
    - Accepts multiple document_ids: ?document_id=1&document_id=2&document_id=3
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    if not document_id or len(document_id) == 0:
        raise HTTPException(status_code=400, detail="At least one document_id is required")
    
    try:
        return StreamingResponse(
            rag_query_stream(
                query=query.strip(),
                db=db,
                limit=limit,
                score_threshold=score_threshold,
                document_ids=document_id
            ),
            media_type="text/event-stream"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query stream failed: {str(e)}")


@router.post("/ask")
def rag_search_query(
    query: str = Query(..., min_length=1, description="Query to answer"),
    document_id: Optional[list[int]] = Query(None, description="Optional Document ID(s) to query within"),
    limit: int = Query(5, ge=1, le=20, description="Number of chunks to retrieve"),
    score_threshold: float = Query(0.3, ge=0.0, le=1.0, description="Minimum similarity score"),
    db: Session = Depends(get_db)
):
    """
    Non-streaming RAG query. Returns a single JSON object with answer and citations.
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        result = rag_query(
            query=query.strip(),
            db=db,
            limit=limit,
            score_threshold=score_threshold,
            document_ids=document_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")
