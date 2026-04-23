import cv2
import numpy as np
import fitz  # PyMuPDF
import re
import hashlib
import requests
import json
import os
import uuid
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import SessionLocal, Document
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = FastAPI(title="DocuMind Local AI Backend")

# Setup robust Connection Pooling for Ollama
# This prevents "Connection Refused" issues on high-latency CPU loads
ai_session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
ai_session.mount('http://', HTTPAdapter(max_retries=retries))

# DB Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Allow requests from the Electron/Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "DocuMind Backend"}

# Ensure uploads directory exists and mount it
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ─────────────────────────────────────────────────────────────────
# Fix #4: Sanitize nested objects / arrays → readable strings
# ─────────────────────────────────────────────────────────────────
def sanitize_value(val) -> str:
    """Recursively flatten any nested dict/list to a clean, human-readable string."""
    if isinstance(val, dict):
        return ", ".join(f"{k}: {sanitize_value(v)}" for k, v in val.items())
    elif isinstance(val, list):
        return " | ".join(sanitize_value(item) for item in val)
    else:
        return str(val).strip()

def sanitize_extracted(extracted: dict) -> dict:
    return {k: sanitize_value(v) for k, v in extracted.items()}

# ─────────────────────────────────────────────────────────────────
# Fix #1: Reliable heuristic fallback extraction (zero dependencies)
# ─────────────────────────────────────────────────────────────────
def classify_document(full_text: str) -> str:
    text_lower = full_text.lower()
    if any(w in text_lower for w in ["resume", "curriculum vitae", "work experience", "education", "skills"]):
        return "Resume / CV"
    elif any(w in text_lower for w in ["agreement", "contract", "parties", "hereby", "hereinafter", "nda", "arbitration"]):
        return "Legal Contract"
    elif any(w in text_lower for w in ["bank statement", "account summary", "beginning balance", "statement period"]):
        return "Bank Statement"
    elif any(w in text_lower for w in ["purchase order", "p.o. number", "ship to", "vendor code"]):
        return "Purchase Order"
    elif any(w in text_lower for w in ["receipt", "cashier", "change due", "auth code", "thank you for your purchase"]):
        return "Receipt"
    elif any(w in text_lower for w in ["invoice", "bill to", "amount due", "payment terms", "due date"]):
        return "Invoice"
    elif any(w in text_lower for w in ["w-2", "wage", "federal income tax withheld", "form 1099"]):
        return "Tax Document"
    return "General Document"

def heuristic_extraction(text_lines: list) -> tuple[str, dict]:
    """CPU-only, zero-dependency extraction. Always works."""
    full_text = " ".join(text_lines)
    doc_type = classify_document(full_text)
    extracted = {}

    if doc_type == "Resume / CV":
        # Best effort greedy extraction for fallback
        phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', full_text)
        extracted["Phone Number"] = phone_match.group(0) if phone_match else "Not found"
        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}', full_text)
        extracted["Email"] = email_match.group(0) if email_match else "Not found"
        extracted["Applicant Name"] = text_lines[0].strip()[:50] if text_lines else "Not found"
        
    elif doc_type == "Legal Contract":
        date_match = re.search(r'(?:dated|effective as of|entered into)[\s,]*([A-Z][a-z]+ \d{1,2},?\s*\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', full_text, re.IGNORECASE)
        extracted["Effective Date"] = date_match.group(1).strip() if date_match else "Not specified"
        parties = re.findall(r'"([A-Z][a-zA-Z\s,\.]+(?:LLC|Inc|Ltd|Corp|Company|LLP)?)"', full_text)
        extracted["Parties"] = " and ".join(parties[:2]) if parties else "See document"
        term_match = re.search(r'(?:term|duration|expires?|termination)[\s:]*(\d+\s*(?:year|month|day)s?)', full_text, re.IGNORECASE)
        extracted["Term / Duration"] = term_match.group(1).strip() if term_match else "Not specified"

    elif doc_type == "Bank Statement":
        acct_match = re.search(r'(?:Account (?:Number|No\.?)|Acct\.?)[:\s]*([X*\d]{4,}[-\d]*)', full_text, re.IGNORECASE)
        extracted["Account Number"] = acct_match.group(1).strip() if acct_match else "Redacted / Not found"
        open_bal = re.search(r'(?:Opening|Beginning) Balance[\s:$]*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        extracted["Opening Balance"] = open_bal.group(1) if open_bal else "Not found"
        close_bal = re.search(r'(?:Closing|Ending) Balance[\s:$]*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        extracted["Closing Balance"] = close_bal.group(1) if close_bal else "Not found"
        period = re.search(r'(?:Statement Period|Period)[:\s]*(.+?)(?:\n|  )', full_text, re.IGNORECASE)
        extracted["Statement Period"] = period.group(1).strip() if period else "See document"

    elif doc_type == "Tax Document":
        employer_match = re.search(r"Employer'?s? Name[:\s]+(.+?)(?:\n)", full_text, re.IGNORECASE)
        extracted["Employer"] = employer_match.group(1).strip() if employer_match else text_lines[0] if text_lines else "Not found"
        wages_match = re.search(r'(?:Wages|Box 1)[:\s$]*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        extracted["Wages / Compensation"] = wages_match.group(1) if wages_match else "Not found"
        tax_match = re.search(r'(?:Federal income tax withheld|Box 2)[:\s$]*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        extracted["Federal Tax Withheld"] = tax_match.group(1) if tax_match else "Not found"

    else:  # Invoice, Receipt, Purchase Order, General
        if text_lines:
            extracted["Issuer / Vendor"] = text_lines[0].strip()
        ref_match = re.search(r'(?:INV|Invoice|Receipt|Order|Ref|No\.?)[\s#:\-]*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
        extracted["Reference Number"] = ref_match.group(1).strip() if ref_match else "Not found"
        date_match = re.search(r'(?:Date|Issued)[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|[A-Z][a-z]+ \d{1,2},?\s*\d{4})', full_text, re.IGNORECASE)
        extracted["Date"] = date_match.group(1).strip() if date_match else "Not found"
        total_match = re.search(r'(?:Total|Amount Due|Grand Total|Balance Due)[:\s]*([$₹€£])?\s*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
        if total_match:
            currency = total_match.group(1) or ""
            extracted["Total Amount"] = f"{currency}{total_match.group(2)}"

    return doc_type, extracted

# ─────────────────────────────────────────────────────────────────
# Primary: Try Ollama LLM, fall back to heuristics on any failure
# ─────────────────────────────────────────────────────────────────
def extract_entities(text_lines: list) -> tuple[str, dict]:
    full_text = " ".join(text_lines)
    # Aggressive truncation for tiny 0.5B model context stability
    truncated_text = full_text[:8000]

    prompt = f"""You are a professional document intelligence engine for business SMEs.
Output ONLY raw valid JSON — no markdown, no explanation, no extra text.

Analyze the document text below. Return a JSON object formatted exactly like this example, but replace the keys and values with ALL the relevant data points you find in the underlying text:
{{
  "document_type": "Resume",
  "extracted": {{
    "Applicant Name": "Deven Patel",
    "Email Address": "deven@example.com",
    "Location": "Noida, UP",
    "Skills": "Python, React",
    "Phone Number": "Not found"
  }}
}}

Rules:
1. The "document_type" should accurately categorize what the document is (e.g. Purchase Order, Resume, Legal Contract, Invoice).
2. The "extracted" dictionary MUST contain the actual real names of the fields you find. Do NOT output generic keys like "Data Point 1". Make up the best descriptive key possible.
3. Extract AS MANY relevant fields as possible. Do not limit yourself. If there are 15 important fields in the document, extract all 15.
4. Every value MUST be a readable string. If an important field is missing, write "Not found".

DOCUMENT TEXT:
{truncated_text}
"""

    try:
        # Fix #1: Use persistent session and 120s timeout
        response = ai_session.post('http://127.0.0.1:11434/api/generate', json={
            "model": "qwen2.5:0.5b",
            "prompt": prompt,
            "format": "json",
            "stream": False
        }, timeout=120)
        response.raise_for_status()
        llm_output = response.json().get('response', '')
        parsed = json.loads(llm_output)
        doc_type = parsed.get("document_type", "General Document")
        extracted = parsed.get("extracted", {})
        if not isinstance(extracted, dict) or not extracted:
            raise ValueError("Empty or malformed extracted block from LLM")
        return doc_type, sanitize_extracted(extracted)

    except Exception as e:
        print(f"[DocuMind] Ollama Engine Busy/Unavailable. Root Cause: {e}")
        # Fix #1: Heuristic fallback ensures UI never fails even if Ollama crashes
        doc_type, extracted = heuristic_extraction(text_lines)
        return doc_type, sanitize_extracted(extracted)


# ─────────────────────────────────────────────────────────────────
# Upload Endpoint
# ─────────────────────────────────────────────────────────────────
@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    contents = await file.read()

    # Calculate fingerprint first
    file_hash = hashlib.sha256(contents).hexdigest()
    
    # Fix #2: Atomic logic - check duplicate early but don't commit until very end
    existing_doc = db.query(Document).filter(Document.file_hash == file_hash).first()
    if existing_doc:
        raise HTTPException(status_code=400, detail="Duplicate document detected. This exactly identical file is already in your Repository.")

    # Save file permanently to local storage
    file_uuid = str(uuid.uuid4())
    safe_filename = "".join([c for c in file.filename if c.isalnum() or c in ".-_"])
    local_filename = f"{file_uuid}_{safe_filename}"
    file_path = os.path.join(UPLOAD_DIR, local_filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    # Extract raw text from PDF/Images
    raw_text = []
    try:
        if file.filename.lower().endswith(".pdf"):
            doc = fitz.open("pdf", contents)
            for page in doc:
                raw_text.extend(page.get_text().split('\n'))
            raw_text = [t.strip() for t in raw_text if t.strip()]
        else:
            # Simple fallback for images for now
            raw_text = ["Image Document", f"Filename: {file.filename}", "OCR Pending..."]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to read file content: {str(e)}")

    # Extraction step (can take 60s+ on CPU)
    doc_type, extracted_data = extract_entities(raw_text)

    # Final DB commit only happens IF we reached this line successfully
    try:
        new_doc = Document(
            filename=file.filename,
            document_type=doc_type,
            extracted_data=extracted_data,
            file_hash=file_hash,
            file_path=f"/uploads/{local_filename}"
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
    except Exception as e:
        db.rollback()
        # Clean up the dangling file if DB commit bombs out
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Database commit failed: {str(e)}")

    return {
        "id": new_doc.id,
        "filename": new_doc.filename,
        "message": "File processed successfully.",
        "document_type": new_doc.document_type,
        "extracted": new_doc.extracted_data,
    }

@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "document_type": d.document_type,
            "extracted": d.extracted_data,
            "file_path": d.file_path,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    # Try to delete the physical file first
    if doc.file_path:
        # doc.file_path looks like "/uploads/xxx.pdf", convert to local path
        local_path = doc.file_path.lstrip("/")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                print(f"File cleanup warning: {e}")

    # Remove from DB
    db.delete(doc)
    db.commit()
    return {"message": "Document successfully deleted from vault."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
