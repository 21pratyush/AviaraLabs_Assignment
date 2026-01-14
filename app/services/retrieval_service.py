from typing import List, Dict, Optional
import os
from sqlalchemy.orm import Session
from qdrant_client.models import PointIdsList, Filter, FieldCondition, MatchValue

from app.services.embedding_service import get_embedding_model
from app.db.vector_db import get_qdrant_client
from app.core.config import COLLECTION_NAME
from app.services.ai.llm import get_gemini
from app.db.models import DocumentChunk, Document
from langchain_core.messages import HumanMessage

version = "v1"

def vector_search(
    query: str,
    db: Session,
    limit: int = 5,
    score_threshold: float = 0.3,
    document_ids: Optional[List[int]] = None
) -> Dict:
    """
    Search for documents similar to the query.
    
    Args:
        query: Search query text
        db: Database session
        limit: Number of results to return
        score_threshold: Minimum similarity score (0-1)
        document_ids: Optional list of document IDs to filter results to specific documents
        
    Returns:
        Dict with search results containing chunks and metadata
    """
    
    try:
        # Create embedding for query
        embedding_model = get_embedding_model()
        query_embedding = embedding_model.encode(query, show_progress_bar=False).tolist()
        
        # Build filter if document_ids are provided
        query_filter = None
        if document_ids and len(document_ids) > 0:
            if len(document_ids) == 1:
                # Single document - use must condition
                query_filter = Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_ids[0])
                        )
                    ]
                )
            else:
                # Multiple documents - use should condition (OR logic)
                query_filter = Filter(
                    should=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=doc_id)
                        )
                        for doc_id in document_ids
                    ]
                )
        
        # Search in Qdrant
        qdrant_client = get_qdrant_client()
        search_results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
            with_vectors=False
        )
        
        # Enrich results with DB data
        results = []
        for result in search_results.points:
            # Skip results below threshold
            if result.score < score_threshold:
                continue
            
            vector_id = result.id
            chunk_text = result.payload.get("text")
            document_id = result.payload.get("document_id")
            chunk_index = result.payload.get("chunk_index")
            
            # Get document and chunk metadata from DB
            doc = db.query(Document).filter(Document.id == document_id).first()
            chunk = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.vector_id == str(vector_id)
            ).first()
            
            results.append({
                "vector_id": vector_id,
                "score": result.score,
                "chunk_text": chunk_text,
                "chunk_id": chunk.id if chunk else None,
                "document_id": document_id,
                "document_filename": doc.filename if doc else None,
                "chunk_index": chunk_index
            })
        
        return {
            "status": "success",
            "query": query,
            "result_count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {
            "status": "error",
            "query": query,
            "error": str(e),
            "results": []
        }


def rag_query_stream(
    query: str,
    db: Session,
    limit: int = 5,
    score_threshold: float = 0.3,
    document_ids: Optional[List[int]] = None
):
    """
    RAG Query with streaming: Search documents and stream AI answer using Gemini.
    
    Args:
        query: Search query text
        db: Database session
        limit: Number of results to return
        score_threshold: Minimum similarity score (0-1)
        document_ids: Optional list of document IDs to filter results to specific documents
    
    Yields:
        - JSON strings with metadata
        - Streamed answer chunks
    """
    
    try:
        # Search for relevant documents
        search_results = vector_search(
            query=query,
            db=db,
            limit=limit,
            score_threshold=score_threshold,
            document_ids=document_ids
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"RAG Search Results: {search_results}")
        
        if search_results["status"] != "success" or not search_results["results"]:
            yield '{"status": "success", "query": "'+ query +'", "answer": "No relevant documents found for your query.", "retrieved_chunks": [], "sources": []}'
            return
        
        # Prepare sources
        sources = list(set([
            result['document_filename'] 
            for result in search_results["results"]
        ]))
        
        # Stream metadata first
        yield f'{{"status": "searching", "query": "{query}", "chunk_count": {len(search_results["results"])}, "sources": {sources}}}\n'
        
        # Load RAG prompt
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            f"../prompts/rag_query_prompt_{version}.txt"
        )
        with open(prompt_path, "r") as f:
            system_prompt = f.read()
        
        # Prepare context from retrieved chunks
        context = "\n\n".join([
            f"[Document: {result['document_filename']}]\n{result['chunk_text']}"
            for result in search_results["results"]
        ])
        
        # Stream response from Gemini
        llm = get_gemini()

        user_message = f"""{system_prompt} USER QUESTION: {query} RETRIEVED DOCUMENTS: {context} ANSWER:"""
        
        message = HumanMessage(content=user_message)
        
        # Stream the response
        yield '{"status": "generating", "message": "Generating answer..."}\n'
        
        # Use streaming with LLM
        full_answer = ""
        for chunk in llm.stream([message]):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content
                full_answer += content
                # Escape newlines and quotes for JSON
                escaped_content = content.replace('"', '\\"').replace('\n', '\\n')
                yield f'{{"type": "answer_chunk", "data": "{escaped_content}"}}\n'
        
        # Send final response with all metadata
        yield f'{{"status": "success", "query": "{query}", "chunk_count": {len(search_results["results"])}, "sources": {sources}, "complete": true}}\n'
        
    except Exception as e:
        yield f'{{"status": "error", "error": "{str(e)}"}}\n'
