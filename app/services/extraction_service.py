import os
import json
from typing import Dict, List
from sqlalchemy.orm import Session

from docling.document_converter import DocumentConverter
from langchain_core.messages import HumanMessage

from app.db.models import Document, Extraction, DocumentChunk
from app.services.ai.llm import get_gemini
from app.services.embedding_service import create_embeddings
from app.services.qdrant_service import store_embeddings
from app.services.ingest_service import save_document_chunks, save_extraction_result

version = "v1"

## util function to parse JSON from Gemini response
def parse_json_garbage(text: str) -> dict:
    """Helper to clean Gemini's markdown backticks and find JSON"""
    import re, json
    json_match = re.search(r'\{.*\}', text.strip(), re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    raise json.JSONDecodeError("No JSON found", text, 0)

## Extraction Service Functions
def extract_documents_raw_text(
    db: Session,
    document_ids: List[int]
) -> Dict[int, Dict]:
    """
    Phase-1 Extraction (Validation Phase)

    - Load PDFs from disk
    - Extract raw text using Docling
    - Return extracted text with metadata
    - NO Gemini
    - NO chunking
    - NO DB writes
    """

    results: Dict[int, Dict] = {}
    converter = DocumentConverter()

    for document_id in document_ids:
        doc = db.query(Document).filter(Document.id == document_id).first()

        if not doc:
            results[document_id] = {"error": "Document not found"}
            continue

        if not doc.file_path or not os.path.exists(doc.file_path):
            results[document_id] = {"error": "File missing on disk"}
            continue

        try:
            conversion_result = converter.convert(doc.file_path)
            extracted_text = conversion_result.document.export_to_text()
        except Exception as e:
            results[document_id] = {
                "error": f"Docling extraction failed: {str(e)}"
            }
            continue
    
        results[document_id] = {
            "filename": doc.filename,
            "extracted_text": extracted_text,
            "text_preview": extracted_text[:2000],
            "text_length": len(extracted_text)
        }
    
    return results

def extract_contract_data(
    db: Session,
    document_ids: List[int]
) -> Dict[int, Dict]:
    """
    Phase-2 Extraction (Gemini-based structured extraction)
    
    - Load PDFs from disk
    - Extract raw text using Docling
    - Send to Gemini for structured extraction
    - Return extracted JSON data
    - No strict validation - proceed even if some fields are missing
    """
    
    raw_extractions = extract_documents_raw_text(db, document_ids)
    results: Dict[int, Dict] = {}
    llm = get_gemini()
    
    # Load prompt
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        f"../prompts/extraction_prompt_{version}.txt"
    )
    with open(prompt_path, "r") as f:
        extraction_prompt = f.read()
    
    for document_id, data in raw_extractions.items():
        # Check if Phase-1 failed
        if "error" in data:
            results[document_id] = data
            continue
        extracted_text = data["extracted_text"]
        
        try:
            message = HumanMessage(
                content=f"{extraction_prompt}\n\nCONTRACT TEXT:\n{extracted_text}"
            )
            response = llm.invoke([message])
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            if not response_text or not response_text.strip():
                results[document_id] = {
                    "error": "Empty response from Gemini",
                    "extracted_data": None
                }
                continue
            
            extracted_json = parse_json_garbage(response_text)
            
            results[document_id] = {
                "filename": data["filename"],
                "extracted_data": extracted_json,
                "status": "success"
            }
            
            # Save to database
            try:
                save_extraction_result(
                    db=db,
                    document_id=document_id,
                    extracted_json=extracted_json,
                    model_used="gemini-2.5-flash"
                )
            except Exception as db_error:
                results[document_id]["db_error"] = f"Failed to save to DB: {str(db_error)}"
            
        except json.JSONDecodeError as e:
            results[document_id] = {
                "error": f"JSON parsing failed: {str(e)}",
                "extracted_data": None
            }
        except Exception as e:
            results[document_id] = {
                "error": f"Extraction failed: {str(e)}",
                "extracted_data": None
            }
    
    return results

## Embedding Creation Function
def process_document_embeddings(
    db: Session,
    document_ids: List[int],
) -> Dict[int, Dict]:
    """
    Phase-3 Embeddings (Create embeddings from document text)
    
    - Reuses extract_documents_raw_text() for PDF extraction
    - Chunk text and create embeddings
    - Store in Qdrant
    - Save chunks to DocumentChunk table
    - Return vector IDs
    """
    
    raw_extractions = extract_documents_raw_text(db, document_ids)
    results: Dict[int, Dict] = {}
    
    for document_id, data in raw_extractions.items():
        try:
            # Check if Phase-1 failed
            if "error" in data:
                results[document_id] = {
                    "error": data["error"],
                    "vector_ids": None
                }
                continue
            
            extracted_text = data["extracted_text"]
            filename = data["filename"]
            
            # Create embeddings
            embeddings_data = create_embeddings(extracted_text)
            
            # Calculate vector IDs once
            vector_ids = [int((document_id * 10000) + idx) for idx in range(len(embeddings_data["chunks"]))]
            
            # Prepare chunk data with vector IDs for DB storage
            chunks_with_ids = [
                {
                    "text": chunk["text"],
                    "vector_id": vector_id
                }
                for chunk, vector_id in zip(embeddings_data["chunks"], vector_ids)
            ]
            
            # Prepare chunks with embeddings AND vector IDs for Qdrant storage
            chunks_with_embeddings_and_ids = [
                {
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "vector_id": vector_id,
                    "chunk_index": idx
                }
                for idx, (chunk, vector_id) in enumerate(zip(embeddings_data["chunks"], vector_ids))
            ]
            
            # FIRST: Save chunks to DB
            try:
                chunk_ids = save_document_chunks(
                    db=db,
                    document_id=document_id,
                    chunks_data=chunks_with_ids
                )
            except Exception as db_error:
                results[document_id] = {
                    "error": f"DB save failed: {str(db_error)}",
                    "vector_ids": None
                }
                continue
            
            # SECOND: Store in Qdrant and get vector IDs
            qdrant_result = store_embeddings(
                document_id=document_id,
                chunks_with_embeddings=chunks_with_embeddings_and_ids
            )
            
            if qdrant_result["status"] != "success":
                results[document_id] = {
                    "error": qdrant_result.get("error", "Qdrant storage failed"),
                    "vector_ids": None
                }
                continue
            
            results[document_id] = {
                "filename": filename,
                "status": "success",
                "vector_ids": qdrant_result["vector_ids"],
                "chunk_count": len(qdrant_result["vector_ids"]),
                "db_chunk_ids": chunk_ids
            }
            
        except Exception as e:
            results[document_id] = {
                "error": f"Embedding creation failed: {str(e)}",
                "vector_ids": None
            }
    
    return results