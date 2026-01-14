import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, AuditFinding


def _find_matches_in_chunk(patterns: List[re.Pattern], text: str) -> List[Dict[str, Any]]:
    matches = []
    for pat_name, pat in patterns:
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            matches.append({
                "pattern": pat_name,
                "match_text": text[start:end],
                "start": start,
                "end": end
            })
    return matches


def scan_documents_for_risks(db: Session, document_ids: List[int]) -> Dict[int, List[Dict]]:
    """
    Scan provided documents (by document_id) for common risky clauses.

    Returns a mapping document_id -> list of findings.
    Each finding contains clause_type, severity, description, and evidence (chunk, offsets).
    """
    # Define heuristics as regex patterns
    auto_renewal_patterns = [
        ("auto_renewal", re.compile(r"auto[- ]?renew", re.I)),
        ("renewal_notice_days", re.compile(r"notice.*?(\d{1,3})\s+day", re.I)),
    ]

    indemnity_patterns = [
        ("indemnify", re.compile(r"indemnif[y|ication|ies]?|hold harmless", re.I)),
    ]

    liability_patterns = [
        ("unlimited_liability", re.compile(r"unlimited\s+liabilit|no\s+liability\s+cap|no\s+cap\s+on\s+liability", re.I)),
        ("liability_cap_absent", re.compile(r"liabilit(y|ies).*?cap|cap\s+on\s+liability", re.I)),
    ]

    findings_by_doc: Dict[int, List[Dict]] = {}

    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(document_ids)).all()

    for chunk in chunks:
        doc_id = chunk.document_id
        text = (chunk.chunk_text or "")
        doc_findings = findings_by_doc.setdefault(doc_id, [])

        # Auto-renewal checks
        auto_matches = _find_matches_in_chunk(auto_renewal_patterns, text)
        for m in auto_matches:
            # If renewal_notice_days matched and days < 30 -> high severity
            if m["pattern"] == "renewal_notice_days":
                try:
                    days = int(re.search(r"(\d{1,3})", m["match_text"]).group(1))
                except Exception:
                    days = None

                severity = "high" if days is not None and days < 30 else "medium"
                description = f"Auto-renewal with notice period {days} days" if days else "Auto-renewal clause with notice requirement"
            else:
                severity = "medium"
                description = "Auto-renewal clause detected"

            evidence = {
                "chunk_id": chunk.id,
                "vector_id": chunk.vector_id,
                "text_snippet": text[m["start"]:m["end"]],
                "char_start": m["start"],
                "char_end": m["end"]
            }

            finding = {
                "clause_type": "auto_renewal",
                "severity": severity,
                "description": description,
                "evidence": evidence,
            }
            doc_findings.append(finding)

        # Indemnity checks
        indemnity_matches = _find_matches_in_chunk(indemnity_patterns, text)
        for m in indemnity_matches:
            severity = "high" if re.search(r"to the fullest extent|without limit|including all", m["match_text"], re.I) else "medium"
            finding = {
                "clause_type": "indemnity",
                "severity": severity,
                "description": "Indemnity / hold harmless clause detected",
                "evidence": {
                    "chunk_id": chunk.id,
                    "vector_id": chunk.vector_id,
                    "text_snippet": text[m["start"]:m["end"]],
                    "char_start": m["start"],
                    "char_end": m["end"]
                }
            }
            doc_findings.append(finding)

        # Liability checks
        liability_matches = _find_matches_in_chunk(liability_patterns, text)
        for m in liability_matches:
            if m["pattern"] == "unlimited_liability":
                severity = "high"
                desc = "Unlimited or uncapped liability language detected"
            else:
                # If presence of 'cap' indicates some cap; ignore if cap present and numeric
                severity = "medium"
                desc = "Liability cap language detected"

            finding = {
                "clause_type": "liability",
                "severity": severity,
                "description": desc,
                "evidence": {
                    "chunk_id": chunk.id,
                    "vector_id": chunk.vector_id,
                    "text_snippet": text[m["start"]:m["end"]],
                    "char_start": m["start"],
                    "char_end": m["end"]
                }
            }
            doc_findings.append(finding)

    # Persist findings into DB and return structure
    results: Dict[int, List[Dict]] = {}
    for doc_id, findings in findings_by_doc.items():
        results[doc_id] = findings
        # Save into AuditFinding table
        for f in findings:
            af = AuditFinding(
                document_id=doc_id,
                clause_type=f["clause_type"],
                severity=f["severity"],
                description=f["description"],
                evidence=str(f["evidence"])  # store as textified JSON
            )
            db.add(af)
    try:
        db.commit()
    except Exception:
        db.rollback()

    return results
