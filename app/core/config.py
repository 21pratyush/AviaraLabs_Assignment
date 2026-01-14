import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./contracts.db")

UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR", "./data/uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Qdrant(Vector-DB) Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "contracts")
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 produces 384-dim vectors