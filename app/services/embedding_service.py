from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from PyPDF2 import PdfReader


# Lightweight model suitable for CPU
MODEL_NAME = "all-MiniLM-L6-v2"
model = None


def get_embedding_model():
    """Load embedding model (lazy loading)"""
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model


def extract_pages(file_path: str) -> List[str]:
    """Extract text per-page from a PDF using PyPDF2."""
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(text)
    return pages


def chunk_pages(pages: List[str], chunk_size: int = 512, overlap: int = 50) -> List[Dict[str, Any]]:
    """Produce page-aware chunks with page number and char offsets (char ranges relative to page).

    Returns list of dicts: {text, page_number, char_start, char_end}
    """
    chunks = []
    for page_idx, page_text in enumerate(pages, start=1):
        if not page_text or not page_text.strip():
            continue
        step = chunk_size - overlap
        text_len = len(page_text)
        if text_len <= chunk_size:
            chunks.append({
                "text": page_text,
                "page_number": page_idx,
                "char_start": 0,
                "char_end": text_len
            })
            continue

        for i in range(0, text_len, step):
            chunk = page_text[i:i + chunk_size]
            if chunk.strip():
                chunks.append({
                    "text": chunk,
                    "page_number": page_idx,
                    "char_start": i,
                    "char_end": min(i + chunk_size, text_len)
                })

    return chunks


def create_embeddings(file_path: str) -> Dict:
    """Create embeddings for a PDF file, returning page-aware chunks with embeddings.

    Args:
        file_path: Path to PDF file

    Returns:
        Dict with chunks and their embeddings
    """
    embeddings_model = get_embedding_model()

    pages = extract_pages(file_path)
    page_chunks = chunk_pages(pages)

    texts = [c["text"] for c in page_chunks]
    if not texts:
        return {"chunk_count": 0, "model_used": MODEL_NAME, "chunks": []}

    embeddings = embeddings_model.encode(texts, show_progress_bar=False)

    result_chunks = []
    for c, emb in zip(page_chunks, embeddings):
        result_chunks.append({
            "text": c["text"],
            "page_number": c["page_number"],
            "char_start": c["char_start"],
            "char_end": c["char_end"],
            "embedding": emb.tolist()
        })

    return {
        "chunk_count": len(result_chunks),
        "model_used": MODEL_NAME,
        "chunks": result_chunks
    }
