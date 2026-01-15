# tests/test_full_flow.py
"""
End-to-end smoke test that replays the critical path from simulate_test.py
- ingests 2 PDFs
- waits until processing_stage == "indexed"
- runs both audit strategies
- asks one RAG question
All asserts are deterministic (no external webhook needed).
"""
import time
from pathlib import Path
from typing import List, Dict
import pytest
import requests
from requests.exceptions import RequestException

API = "http://localhost:8000/api/v1"
SAMPLES = list(Path(".").glob("*.pdf"))
assert SAMPLES, "Put at least two PDFs in the current dir for testing"



def wait_for_stage(doc_id: int, stage: str = "indexed", timeout: int = 60):
    """Poll /documents/{id} until stage is reached or timeout."""
    for _ in range(timeout):
        r = requests.get(f"{API}/documents/{doc_id}")
        r.raise_for_status()
        if r.json()["processing_stage"] == stage:
            return
        time.sleep(1)
    raise RuntimeError(f"doc {doc_id} never reached stage {stage}")


# ---------- fixtures ----------
@pytest.fixture(scope="module", autouse=True)
def ensure_services():
    """Fail fast if API or Qdrant is not up."""
    try:
        health = requests.get(f"{API}/admin/healthz", timeout=5)
        health.raise_for_status()
    except RequestException as e:
        pytest.exit(f"API not ready: {e}")


# ---------- tests ----------
def test_ingest():
    """POST /documents/upload and obtain document_ids."""
    files = [("files", (p.name, p.open("rb"), "application/pdf")) for p in SAMPLES]
    r = requests.post(f"{API}/documents/upload", files=files)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["count"] == len(SAMPLES)
    assert len(data["document_ids"]) == len(SAMPLES)
    # store globally for later stages
    test_ingest.doc_ids = data["document_ids"]


def test_processing_completes():
    """Wait until all docs are vectorised."""
    for doc_id in test_ingest.doc_ids:
        wait_for_stage(doc_id, "indexed")


def test_extract_exists():
    """GET /documents/{id}/extraction returns valid JSON."""
    for doc_id in test_ingest.doc_ids:
        r = requests.get(f"{API}/documents/{doc_id}/extraction")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "extracted_json" in body
        assert isinstance(body["extracted_json"], dict)


@pytest.mark.parametrize("strategy", ["regex", "ai"])
def test_audit(strategy: str):
    """POST /analysis/audit?strategy=xxx returns findings."""
    r = requests.post(
        f"{API}/analysis/audit",
        params={"strategy": strategy},
        json=test_ingest.doc_ids,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["strategy_used"] == strategy
    results: Dict[str, List] = data["results"]
    # at least one doc had ≥1 finding
    total = sum(len(findings) for findings in results.values())
    assert total > 0, f"No findings for strategy {strategy}"


def test_rag_question():
    """POST /ask returns an answer grounded in chunks."""
    payload = {
        "query": "What is the liability cap?",
        "document_id": test_ingest.doc_ids,
        "limit": 3,
    }
    r = requests.post(f"{API}/ask", params=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "answer" in body
    assert body["answer"] != "No relevant documents found"
    assert len(body["sources"]) >= 1
    assert len(body["retrieved_chunks"]) >= 1


def test_metrics_endpoint():
    """GET /admin/metrics returns counters."""
    r = requests.get(f"{API}/admin/metrics")
    assert r.status_code == 200
    data = r.json()
    assert data["pipeline"]["documents_by_status"]["completed"] >= len(SAMPLES)
    assert data["vector_db"]["total_points"] >= 1