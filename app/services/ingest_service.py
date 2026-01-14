import os
import uuid
from sqlalchemy.orm import Session
from typing import List
from app.db.models import Document
from app.core.config import UPLOAD_DIR

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def ingest_documents(db: Session, files: list) -> List[int]:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    document_ids = []

    for file in files:
        # Validate PDF
        if file.content_type not in ("application/pdf", "application/x-pdf"):
            raise ValueError(f"Unsupported file type: {file.content_type}")

        # Generate unique filename
        filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        # Save to disk
        file_bytes = file.file.read()
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File too large: {file.filename}")
        file.file.seek(0)  # reset pointer
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Save metadata to DB
        doc = Document(
            filename=file.filename,
            content_type=file.content_type,
            file_path=file_path
        )
        db.add(doc)
        db.flush()
        document_ids.append(doc.id)

    db.commit()
    return document_ids
