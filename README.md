# DocuMind

DocuMind is an **Offline, Privacy-First AI Document Intelligence Platform** designed specifically for SMEs. It empowers businesses to automatically classify, extract, and vault complex business documents like Legal Contracts, Resumes, and Purchase Orders directly on their local hardware—without sending a single byte of sensitive data to the cloud.

## Key Features

1. **Local-First Zero-Knowledge Architecture**: All processing happens entirely on your machine.
2. **Dual-Engine Extraction Pipeline**: 
   - Uses **Local AI (Ollama)** for intelligent semantic extraction.
   - Transparently falls back to a Regex engine if the system experiences heavy memory pressure.
3. **Atomic Persistence & Vaulting**: Documents and their physical `pdf/image` files are vaulted into a local SQLite database that ensures no half-saved states or duplications happen.
4. **Intelligent UI / Deep Dive**: A sleek React frontend leveraging dynamic rendering and glassmorphism. It offers a unique 3-column "Deep Dive" repository allowing side-by-side viewing of your original archived PDF alongside mathematically clean, human-readable extracted variables.

## Tech Stack
* **Frontend**: React, Vite, TS, Electron 
* **Backend**: Python, FastAPI, SQLAlchemy, SQLite
* **Document Parsing**: PyMuPDF (`fitz`)
* **AI Engine**: Ollama (`qwen2.5:0.5b` optimized for lightweight 8GB machines)

## Quickstart
### Prerequisites
- Python 3.10+
- Node.js v20+
- [Ollama](https://ollama.com/) (Must be actively running in background)

### Running Locally
You need to operate the dual servers:

**1. FastAPI Backend**
```bash
cd backend
# Create python venv (if not done)
# python -m venv venv
# .\venv\Scripts\activate
# pip install -r requirements.txt
python -m uvicorn main:app --reload
```

**2. Vite Frontend**
```bash
cd frontend
npm install
npm run dev
```

### Future Roadmap
- [ ] Implement Natural Language Semantic Search across all extracted business history.
- [ ] Export directly into CSV/Excel for Account integration workflows.
- [ ] Final package packaging (Windows Executable Installer via Electron).
