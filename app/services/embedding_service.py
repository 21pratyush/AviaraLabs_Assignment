from typing import List, Dict
from sentence_transformers import SentenceTransformer


# Lightweight model suitable for CPU
MODEL_NAME = "all-MiniLM-L6-v2"
model = None

def get_embedding_model():
    """Load embedding model (lazy loading)"""
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """
    Split text into chunks with overlap.
    
    Args:
        text: Input text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Overlap between chunks in characters
        
    Returns:
        List of text chunks
    """
    chunks = []
    step = chunk_size - overlap
    
    if len(text) <= chunk_size:
        return [text]
    
    for i in range(0, len(text), step):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks

def create_embeddings(text: str) -> Dict:
    """
    Create embeddings for text chunks.
    
    Args:
        text: Input text to embed
        
    Returns:
        Dict with chunks and their embeddings
    """
    embeddings_model = get_embedding_model()
    
    # Split into chunks
    chunks = chunk_text(text)
    
    # Generate embeddings
    embeddings = embeddings_model.encode(chunks, show_progress_bar=False)
    
    # Return chunks with embeddings
    result = {
        "chunk_count": len(chunks),
        "model_used": MODEL_NAME,
        "chunks": [
            {
                "text": chunk,
                "embedding": embedding.tolist()
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
    }
    
    return result
