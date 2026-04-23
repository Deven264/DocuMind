import cv2
import numpy as np
import fitz  # PyMuPDF
import re
import hashlib
import requests
import json
import os
import uuid
import chromadb
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import SessionLocal, Document, ChatSession, ChatMessage
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

app = FastAPI(title="DocuMind Local AI Backend")

# Setup robust Connection Pooling for Ollama
# This prevents "Connection Refused" issues on high-latency CPU loads
ai_session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
ai_session.mount('http://', HTTPAdapter(max_retries=retries))

# Vector Database
chroma_client = chromadb.PersistentClient(path="./chroma_db")
vector_collection = chroma_client.get_or_create_collection(name="documind_vectors")

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

    prompt = f"""Extract the key business data from the text below. 
You must output ONLY valid JSON. Extract specific fields directly from the text. 
If an important field is found in the text, invent a short English key for it (like "Company Name", "Total Amount", "Email").

Example Expected Output format:
{{
  "document_type": "Invoice / Resume / Contract [Choose one]",
  "extracted": {{
    "Applicant Name": "Deven Patel",
    "Email": "deven@example.com",
    "Location": "Noida",
    "Total Billed": "$400"
  }}
}}

TEXT TO EXTRACT FROM:
{truncated_text}

OUTPUT JSON ONLY:
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
        
        # ─────────────────────────────────────────────────────────────────
        # Semantic Indexing using Nomic
        # ─────────────────────────────────────────────────────────────────
        full_document_content = " ".join(raw_text)
        vector_payload = f"Type: {doc_type}. Data: {json.dumps(extracted_data)}. Content: {full_document_content[:4000]}"
        try:
            embed_res = ai_session.post('http://127.0.0.1:11434/api/embeddings', json={
                "model": "nomic-embed-text",
                "prompt": vector_payload
            }, timeout=60)
            if embed_res.status_code == 200:
                embedding = embed_res.json().get("embedding")
                vector_collection.add(
                    embeddings=[embedding],
                    documents=[vector_payload],
                    metadatas=[{"filename": file.filename}],
                    ids=[str(new_doc.id)]
                )
        except Exception as e:
            print(f"[DocuMind] Semantic Embedding failed (Document still saved to SQLite): {e}")

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

# ─────────────────────────────────────────────────────────────────
# Chat Sessions CRUD
# ─────────────────────────────────────────────────────────────────

@app.get("/api/chats")
def get_chats(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in sessions]

@app.post("/api/chats")
def create_chat(db: Session = Depends(get_db)):
    session = ChatSession(title="New Chat")
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": session.id, "title": session.title}

@app.get("/api/chats/{session_id}")
def get_chat_messages(session_id: int, db: Session = Depends(get_db)):
    msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "citations": m.citations_json
        } for m in msgs
    ]

@app.delete("/api/chats/{session_id}")
def delete_chat(session_id: int, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session:
        db.delete(session)
        db.commit()
    return {"status": "ok"}

def auto_name_session(session_id: int, user_message: str):
    db = SessionLocal()
    try:
        response = ai_session.post('http://127.0.0.1:11434/api/chat', json={
            "model": "qwen2.5:0.5b",
            "messages": [
                {"role": "system", "content": "You are a title generator. Generate a very short 3-word title for the user's message. Do not use quotes or punctuation. Just return the raw words."},
                {"role": "user", "content": user_message}
            ],
            "stream": False
        }, timeout=20)
        
        if response.status_code == 200:
            title = response.json().get('message', {}).get('content', 'New Chat').strip()
            title = title.replace('"', '').replace("'", "")
            
            chat_session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if chat_session:
                chat_session.title = title[:40]
                db.commit()
    except Exception as e:
        print(f"Auto-naming failed: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────
# RAG Chat Endpoint (Conversational Search)
# ─────────────────────────────────────────────────────────────────
class InboundMessage(BaseModel):
    role: str
    content: str

class ChatPayload(BaseModel):
    session_id: int
    messages: List[InboundMessage]

@app.post("/api/chat")
def chat_with_documents(payload: ChatPayload, bg_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not payload.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
        
    session_id = payload.session_id
    user_query = payload.messages[-1].content
    
    # Check if this is the very first message for auto-naming
    existing_count = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
    if existing_count == 0:
        bg_tasks.add_task(auto_name_session, session_id, user_query)
        
    # Save the User message to DB
    user_db_msg = ChatMessage(session_id=session_id, role="user", content=user_query)
    db.add(user_db_msg)
    db.commit()
    
    # 1. Context Retrieval
    context_str = ""
    
    try:
        embed_res = ai_session.post('http://127.0.0.1:11434/api/embeddings', json={
            "model": "nomic-embed-text",
            "prompt": user_query
        }, timeout=45)
        
        if embed_res.status_code == 200:
            query_embedding = embed_res.json().get("embedding")
            results = vector_collection.query(
                query_embeddings=[query_embedding],
                n_results=7 # Pull 7 to give LLM plenty to filter logically
            )
            
            if results['ids'] and results['ids'][0]:
                doc_ids = [int(i) for i in results['ids'][0]]
                docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
                for d in docs:
                    context_str += f"\n--- Document ID: {d.id} ---\nFilename: {d.filename}\nType: {d.document_type}\nExtracted: {json.dumps(d.extracted_data)}\n"
    except Exception as e:
        print(f"[DocuMind] RAG Vector Retrieval Failed: {e}")

    # 2. System Context Injection
    system_prompt = f"""You are DocuMind Chat, an intelligent and highly detailed document retrieval assistant.
Provide comprehensive and highly detailed answers exactly like ChatGPT would. Elaborate fully on the data you find.

Here are the top database records that MIGHT match their query. It is YOUR job to filter them logically.

<DATABASE_CONTEXT>
{context_str if context_str else "No documents found."}
</DATABASE_CONTEXT>

CRITICAL RULES:
1. ONLY use documents that actually match what the user is asking. If they ask for $5000, do not use $60000. 
2. If none of the documents match, say "I couldn't find a document matching that criteria."
3. VERY IMPORTANT: If you use information from a document, you MUST explicitly cite it by adding `[Citation: X]` at the end of your sentence, where X is the Document ID. (Example: "John is a React developer. [Citation: 4]")
"""

    # 3. Construct Sliding Window History (From Payload)
    history = [{"role": "system", "content": system_prompt}]
    
    recent_msgs = payload.messages[-4:]
    for msg in recent_msgs:
        history.append({"role": msg.role, "content": msg.content})
        
    # 4. Generate Response
    try:
        response = ai_session.post('http://127.0.0.1:11434/api/chat', json={
            "model": "qwen2.5:0.5b",
            "messages": history,
            "stream": False
        }, timeout=120)
        response.raise_for_status()
        
        reply = response.json().get('message', {}).get('content', "I'm having trouble processing that request right now.")
        
        # 5. Extract Citations using Regex
        # Look for [Citation: 12] or similar variations
        citation_matches = re.findall(r'\[Citation:\s*(\d+)\]', reply, re.IGNORECASE)
        # Deduplicate and convert to int
        explicit_doc_ids = list(set([int(x) for x in citation_matches]))
        
        # Pull actual citation documents
        citation_docs = db.query(Document).filter(Document.id.in_(explicit_doc_ids)).all()
        citations_json = [
            {
                "id": d.id,
                "filename": d.filename,
                "document_type": d.document_type,
                "file_path": d.file_path,
                "extracted": d.extracted_data
            } for d in citation_docs
        ]
        
        # Clean the reply to remove the ugly [Citation: X] blocks since the UI renders them below the message
        clean_reply = re.sub(r'\[Citation:\s*\d+\]', '', reply, flags=re.IGNORECASE).strip()
        
        # Save Assistant reply to DB
        ast_db_msg = ChatMessage(session_id=session_id, role="assistant", content=clean_reply, citations_json=citations_json)
        db.add(ast_db_msg)
        db.commit()
        
        return {
            "reply": clean_reply,
            "citations": citations_json
        }
        
    except Exception as e:
        print(f"Chat Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Engine failed to respond: {str(e)}")

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    # Try to delete the physical file first
    if doc.file_path:
        local_path = doc.file_path.lstrip("/")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception as e:
                print(f"File cleanup warning: {e}")

    # Remove from ChromaDB Vector Store
    try:
        vector_collection.delete(ids=[str(doc_id)])
    except Exception as e:
        pass

    # Remove from DB
    db.delete(doc)
    db.commit()
    return {"message": "Document successfully deleted from vault."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
