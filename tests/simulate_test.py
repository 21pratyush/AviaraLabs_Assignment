import requests
import sys
import json
import re
from pathlib import Path


def mask_pii(text: str) -> str:
    """
    Enhanced PII masking for legal and financial documents.
    Covers: Emails, Phones, Credit Cards, SSNs, Addresses, and Currency.
    """
    if not isinstance(text, str):
        return text

    # 1. Emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', "[EMAIL_REDACTED]", text)

    # 2. Phone Numbers (Global/US formats)
    text = re.sub(r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}', "[PHONE_REDACTED]", text)

    # 3. Credit Card Numbers (13-19 digits, hyphens/spaces)
    text = re.sub(r'\b(?:\d[ -]*?){13,19}\b', "[FINANCIAL_REDACTED]", text)

    # 4. Social Security Numbers (SSN - XXX-XX-XXXX)
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', "[ID_REDACTED]", text)

    # 5. Currency Amounts (Handles $, €, £ and decimal values)
    # Masking specific money values is often required in shared legal drafts
    text = re.sub(r'([$£€]|USD|INR)\s?\d+(?:,\d{3})*(?:\.\d{2})?', "[CURRENCY_REDACTED]", text)

    # 6. Physical Addresses (Heuristic-based)
    # Matches common patterns like "123 Main St, City, State"
    address_pattern = r'\d+\s+[A-Z][a-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Way|Blvd|Drive|Dr|Lane|Ln|Suite|Apt|Unit|Sector|Way|Innovation Way)[\w\s,]+'
    text = re.sub(address_pattern, "[ADDRESS_REDACTED]", text)

    return text

# ANSI Colors for a beautiful CLI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class CLIReviewer:
    @staticmethod
    def section(title):
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*20} {title} {'='*20}{Colors.ENDC}")

    @staticmethod
    def log_request(method, endpoint, payload=None):
        print(f"{Colors.BLUE}[REQ]{Colors.ENDC} {method} {endpoint}")
        if payload:
            # Mask payload if it contains sensitive strings
            safe_payload = mask_pii(json.dumps(payload))
            print(f"Payload: {safe_payload}")

    @staticmethod
    def log_success(message, data=None):
        print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} {message}")
        if data:
            safe_data = mask_pii(json.dumps(data, indent=2))
            print(f"{Colors.CYAN}{safe_data}{Colors.ENDC}")

    @staticmethod
    def log_error(message):
        print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}")

# Configuration
BASE_URL = "http://localhost:8000/api/v1"
WEBHOOK_URL = "https://webhook.site/61a7cac7-c723-4eff-8306-1a69e0656285"  ## Replace with your webhook URL
DOCS = list(Path(".").glob("*.pdf"))

def run_simulation():
    rev = CLIReviewer()

    # # --- STEP 1: INGESTION ---
    rev.section("PHASE 1: MULTI-DOC INGESTION")
    files_payload = []
    for doc in DOCS:
        filename = doc.name
        try:
            files_payload.append(('files', (filename, doc.open('rb'), 'application/pdf')))
            print(f"{Colors.BLUE}[FILE FOUND]{Colors.ENDC} Ready: {filename}")
        except FileNotFoundError as e:
            rev.log_error(f"Could not read {filename}: {str(e)}")
            return

    rev.log_request("POST", "/documents/upload", {"callback_url": WEBHOOK_URL})
    response = requests.post(f"{BASE_URL}/documents/upload", files=files_payload, data={"callback_url": WEBHOOK_URL})

    if response.status_code != 200:
        rev.log_error(f"Ingestion failed: {response.text}")
        return

    data = response.json()
    doc_ids = data["document_ids"]
    rev.log_success("Documents Registered", data)

    # --- USER INTERVENTION ---
    print(f"\n{Colors.WARNING}{Colors.BOLD}🔔 ACTION REQUIRED:{Colors.ENDC}")
    print(f"1. Open: {WEBHOOK_URL}")
    print(f"2. Wait for status: {Colors.BOLD}'completed'{Colors.ENDC}")
    confirm = input(f"\nProceed to Analysis? (y/n): ").lower()
    
    if confirm != 'y':
        print("Exiting...")
        sys.exit()

# --- STEP 2: AUDIT (Dual Strategy) ---
    rev.section("PHASE 2: CONTRACT AUDIT (REGEX vs AI)")
    
    strategies = ["regex", "ai"]
    
    for strategy in strategies:
        print(f"\n{Colors.BOLD}{Colors.BLUE}>>> Running Audit Strategy: {strategy.upper()}{Colors.ENDC}")
        
        # Syncing with the latest query param endpoint: /analysis/audit?strategy=ai
        rev.log_request("POST", f"/analysis/audit?strategy={strategy}", doc_ids)
        audit_res = requests.post(
            f"{BASE_URL}/analysis/audit", 
            json=doc_ids, 
            params={"strategy": strategy}
        )
        
        if audit_res.status_code == 200:
            # Note: The response structure from audit_service is doc_id -> list
            results = audit_res.json().get("results", {})
            rev.log_success(f"{strategy.upper()} Audit Complete", {"documents_scanned": len(results)})
            
            for d_id, risks in results.items():
                print(f"  {Colors.BOLD}Document ID: {d_id}{Colors.ENDC}")
                if not risks or "error" in risks[0]:
                    print(f"    {Colors.WARNING}No risks found or error occurred.{Colors.ENDC}")
                    continue
                    
                for r in risks:
                    # Severity-based coloring
                    if r.get('severity') in ['high', 'critical']:
                        sev_color = Colors.FAIL 
                    elif r.get('severity') == 'medium':
                        sev_color = Colors.WARNING
                    else:
                        sev_color = Colors.GREEN
                    clean_desc = mask_pii(r['description'])
                    print(f"    {sev_color}● [{r['severity'].upper()}]{Colors.ENDC} {r['clause_type']}: {clean_desc}")
        else:
            rev.log_error(f"{strategy.upper()} Audit Failed: {audit_res.text}")
            
    # --- STEP 3: RAG ---
    rev.section("PHASE 3: SEMANTIC Q&A (RAG)")
    queries = [
        "What is the monthly rent in the lease?",
        "What is the liability cap in the ToS?",
        "How long is the non-disclosure obligation?"
    ]

    for q in queries:
        rev.log_request("POST", "/ask", {"query": q, "doc_ids": doc_ids})
        rag_payload = {"query": q, "document_id": doc_ids, "limit": 5}
        rag_res = requests.post(f"{BASE_URL}/ask", params=rag_payload)
        
        if rag_res.status_code == 200:
            ans = rag_res.json().get("answer")
            print(f"{Colors.GREEN}🤖 AI:{Colors.ENDC} {mask_pii(ans)}")
        else:
            rev.log_error("RAG failed")

    rev.section("SIMULATION COMPLETE")

if __name__ == "__main__":
    run_simulation()