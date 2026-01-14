from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from app.core.config import QDRANT_HOST, QDRANT_PORT, COLLECTION_NAME, VECTOR_SIZE

# Global client
client = None


def get_qdrant_client():
    """Get or create Qdrant client (lazy loading)"""
    global client
    if client is None:
        client = QdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            prefer_grpc=False
        )
    return client


def init_collection():
    """Initialize collection if it doesn't exist"""
    qdrant_client = get_qdrant_client()
    
    try:
        # Check if collection exists
        qdrant_client.get_collection(COLLECTION_NAME)
    except Exception:
        # Collection doesn't exist, create it
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )

