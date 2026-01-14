from typing import List, Dict
from qdrant_client.models import PointStruct
from app.core.config import COLLECTION_NAME
from app.db.vector_db import get_qdrant_client

def store_embeddings(
    document_id: int,
    chunks_with_embeddings: List[Dict]
) -> Dict:
    """
    Store embeddings in Qdrant and return vector IDs.
    
    Args:
        document_id: ID of the document
        chunks_with_embeddings: List of dicts with 'text', 'embedding', 'vector_id', and 'chunk_index' keys
        
    Returns:
        Dict with status and vector IDs
    """
    qdrant_client = get_qdrant_client()
    
    try:
        # Prepare points for Qdrant
        points = []
        vector_ids = []
        
        for chunk_data in chunks_with_embeddings:
            # Use the pre-calculated vector_id, don't recalculate
            point_id = chunk_data["vector_id"]
            
            point = PointStruct(
                id=point_id,
                vector=chunk_data["embedding"],
                payload={
                    "document_id": document_id,
                    "chunk_index": chunk_data["chunk_index"],
                    "text": chunk_data["text"],
                    "page_number": chunk_data.get("page_number"),
                    "char_start": chunk_data.get("char_start"),
                    "char_end": chunk_data.get("char_end"),
                }
            )
            points.append(point)
            vector_ids.append(point_id)
        
        # Upload to Qdrant
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        
        return {
            "status": "success",
            "vector_ids": vector_ids,
            "chunk_count": len(vector_ids)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "vector_ids": []
        }