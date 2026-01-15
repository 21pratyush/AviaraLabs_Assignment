import os
import json
from typing import Dict, List, Any
from app.db.utils import log_error
from sqlalchemy.orm import Session
import logging
from docling.document_converter import DocumentConverter
from langchain_core.messages import HumanMessage

from app.db.models import Document, Extraction, DocumentChunk
from app.services.ai.llm import get_gemini, call_gemini_with_retry
from app.services.embedding_service import create_embeddings
from app.services.qdrant_service import store_embeddings
from app.services.ingest_service import save_document_chunks, save_extraction_result
from app.utils.parser import parse_json_garbage, smart_truncate

logger = logging.getLogger(__name__)
version = "v1"

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
            # Check if text already exists to skip reprocessing
            if doc.processing_stage in ["text_extracted", "ai_extracted", "indexed"]:
                pass
    
            conversion_result = converter.convert(doc.file_path)
            extracted_text = conversion_result.document.export_to_text()
           
            # STATUS UPDATE: Stage 1 Complete
            doc.processing_stage = "text_extracted"
            db.commit()
        
        except Exception as e:
            doc.status = "failed"
            db.commit()
            log_error(db, document_id, "document_processing", e)
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
    extracted_text: str,
    document_id: int,
    db: Session,
) -> Dict[int, Dict]:
    """
    Phase-2 Extraction (Gemini-based structured extraction)
    - Send to Gemini for structured extraction
    - Return extracted JSON data
    - No strict validation - proceed even if some fields are missing
    """
    results: Dict[int, Dict] = {}
    llm = get_gemini()
    
    # Load prompt
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        f"../prompts/extraction_prompt_{version}.txt"
    )
    with open(prompt_path, "r") as f:
        extraction_prompt = f.read()
        
    try:
        message = HumanMessage(content=f"{extraction_prompt}\n\nCONTRACT TEXT:\n{extracted_text}")
        
        response = call_gemini_with_retry(llm, [message])
        
        response_text = response.content if hasattr(response, 'content') else str(response)

        if not response_text or not response_text.strip():
            results[document_id] = {
                    "error": "Empty response from Gemini",
                    "extracted_data": None
                }
            
        extracted_json = parse_json_garbage(response_text)
            
        results[document_id] = {
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
        log_error(db, document_id, "document_processing", e)
        results[document_id] = {
            "error": f"Extraction failed: {str(e)}",
            "extracted_data": None
        }
        raise e
    
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
        # Check if Phase-1 failed
        if "error" in data:
            results[document_id] = {
                "error": data["error"],
                "vector_ids": None
            }
            continue
        doc = db.query(Document).filter(Document.id == document_id).first()
            
        try:
            extracted_text = data["extracted_text"]
            
            # Phase 2: Structured Data (AI)
            if doc.processing_stage == "text_extracted":
                try:
                    optimized_text = smart_truncate(extracted_text)
                    extract_contract_data(optimized_text, document_id, db)  # This populates your 'extractions' table (Signatures, Parties, etc.)
                    
                    doc.processing_stage = "ai_extracted"
                    db.commit()
                except Exception as e:
                    doc.status = "failed"
                    db.commit()
                    logger.error(f"Structured extraction failed for {document_id}: {e}")
                    continue # Skip to next document
                    
            filename = data["filename"]
            # Create embeddings (page-aware) using the stored file path
            if not doc or not doc.file_path:
                results[document_id] = {"error": "Missing file for embeddings", "vector_ids": None}
                continue
            
            # Phase 3: Vector Store
            if doc.processing_stage == "ai_extracted":
                embeddings_data = create_embeddings(doc.file_path)
            
                # Calculate vector IDs once
                vector_ids = [int((document_id * 10000) + idx) for idx in range(len(embeddings_data["chunks"]))]
            
                # Prepare chunk data with vector IDs for DB storage
                chunks_with_ids = [{**c, "vector_id": vid} for c, vid in zip(embeddings_data["chunks"], vector_ids)]
            
                # Prepare chunks with embeddings AND vector IDs for Qdrant storage
                chunks_with_embeddings_and_ids = [
                    {
                        "text": chunk["text"],
                        "embedding": chunk["embedding"],
                        "vector_id": vector_id,
                        "chunk_index": idx,
                        "page_number": chunk.get("page_number"),
                        "char_start": chunk.get("char_start"),
                        "char_end": chunk.get("char_end")
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
                
                # FINAL STATUS UPDATE
                doc.processing_stage = "indexed"
                doc.status = "completed"
                db.commit()
            
            results[document_id] = {
                "filename": filename,
                "status": "success",
                "vector_ids": qdrant_result["vector_ids"],
                "chunk_count": len(qdrant_result["vector_ids"]),
                "db_chunk_ids": chunk_ids
            }
            
        except Exception as e:
            doc.status = "failed"
            db.commit()
            log_error(db, document_id, "document_processing", e)
            results[document_id] = {
                "error": f"Embedding creation failed: {str(e)}",
                "vector_ids": None
            }
    
    return results