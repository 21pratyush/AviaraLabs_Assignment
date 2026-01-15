import re
import json
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import DocumentChunk, AuditFinding, Extraction
from app.services.ai.llm import get_gemini, call_gemini_with_retry
from langchain_core.messages import HumanMessage
from app.utils.parser import parse_json_garbage

logger = logging.getLogger(__name__)

def scan_documents_for_risks(db: Session, document_ids: List[int], strategy: str = "regex") -> Dict[int, List[Dict]]:
    """
    Main entry point for auditing. 
    Supports 'regex' (Heuristic) and 'ai' (LLM-based) strategies.
    """
    results = {}
    for doc_id in document_ids:
        try:
            if strategy == "ai":
                findings = run_ai_audit(db, doc_id)
            else:
                findings = run_regex_audit(db, doc_id)
            
            results[doc_id] = findings
            persist_findings(db, doc_id, findings)
        except Exception as e:
            logger.error(f"Audit failed for doc {doc_id} using {strategy}: {str(e)}")
            results[doc_id] = [{"error": str(e)}]
            
    return results

def run_regex_audit(db: Session, doc_id: int) -> List[Dict]:
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
    findings = []
    
    # Broader patterns to catch variations found in your PDFs
    patterns = {
        "auto_renewal": re.compile(r"auto[- ]?renew|automatically\s+renews", re.I),
        "short_notice": re.compile(r"notice.*?(\d{1,3})\s*days?", re.I),
        # Catch both 'unlimited' AND 'not exceed' (to check small amounts)
        "liability": re.compile(r"unlimited\s+liability|liability\s+shall\s+not\s+exceed", re.I),
        "indemnity": re.compile(r"indemnify|hold\s+harmless|indemnity", re.I)
    }

    for chunk in chunks:
        text = chunk.chunk_text
        
        # 1. Auto-Renewal Check
        if patterns["auto_renewal"].search(text):
            notice_match = patterns["short_notice"].search(text)
            # If notice is found, check if it's < 30. If not found, flag as a potential 'sneaky' renewal.
            days = int(notice_match.group(1)) if notice_match else None
            if days is not None and days < 30:
                findings.append({
                    "clause_type": "auto_renewal",
                    "severity": "high",
                    "description": f"Risky auto-renewal with short notice ({days} days).",
                    "evidence": {"text": text[:200], "page": chunk.page_number}
                })

        # 2. Liability Check (Catching the $50 cap)
        lib_match = patterns["liability"].search(text)
        if lib_match:
            # If it says 'not exceed', let's look for a small dollar amount nearby
            amount_match = re.search(r"\$\s*(\d+)", text[lib_match.end():lib_match.end()+20])
            is_low_cap = amount_match and int(amount_match.group(1)) < 100
            
            if "unlimited" in lib_match.group().lower() or is_low_cap:
                findings.append({
                    "clause_type": "liability",
                    "severity": "critical",
                    "description": f"Critical liability risk: {lib_match.group()}" + (f" (${amount_match.group(1)})" if is_low_cap else ""),
                    "evidence": {"text": text[max(0, lib_match.start()-20):lib_match.end()+30], "page": chunk.page_number}
                })

        # 3. Indemnity Check
        if patterns["indemnity"].search(text):
            findings.append({
                "clause_type": "indemnity",
                "severity": "medium",
                "description": "Indemnity clause detected. Requires manual review for breadth.",
                "evidence": {"text": text[:200], "page": chunk.page_number}
            })

    return findings

def run_ai_audit(db: Session, doc_id: int) -> List[Dict]:
    """
    AI-based audit using the pre-populated Extraction table.
    """    
    # Fetch structured data from Phase 2
    extraction = db.query(Extraction).filter(Extraction.document_id == doc_id).first()
    
    if not extraction:
        raise ValueError("Structured extraction data not found. Please run ingest/extract first.")

    llm = get_gemini()
    
    
    # Prompting the LLM to analyze the JSON structure for specific risks
    audit_prompt = f"""
    You are a senior legal auditor. Review the following structured contract data and identify risks.
    
    REQUIREMENTS:
    1. Flag 'auto_renewal' as HIGH risk if notice is less than 30 days.
    2. Flag 'liability_cap' as CRITICAL if it is 'unlimited' or extremely low (e.g., < $100).
    3. Flag 'indemnity' as MEDIUM if it is 'broad'.
    
    DATA:
    {json.dumps(extraction.extracted_json, indent=2)}
    
    RETURN ONLY a JSON list of objects:
    [{{"clause_type": "string", "severity": "low|medium|high|critical", "description": "string", "evidence": "string"}}]
    """
    response = call_gemini_with_retry(llm, [HumanMessage(content=audit_prompt)])
    
    return parse_json_garbage(response.content)

def persist_findings(db: Session, doc_id: int, findings: List[Dict]):
    """Saves findings to the audit_findings table."""
    # Clear old findings for this doc to avoid duplicates during retries
    db.query(AuditFinding).filter(AuditFinding.document_id == doc_id).delete()
    
    for f in findings:
        if "error" in f: continue
        finding = AuditFinding(
            document_id=doc_id,
            clause_type=f.get("clause_type", "unknown"),
            severity=f.get("severity", "medium"),
            description=f.get("description", ""),
            evidence=f.get("evidence", {})
        )
        db.add(finding)
    db.commit()