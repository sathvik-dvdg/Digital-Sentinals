# PII Shield — Document PII Detection & Redaction Tool

> **Privacy-First. Local-Only. Document Security.**

PII Shield is a high-performance, client-side focused document scanner that detects and redacts Personally Identifiable Information (PII) from PDF, PNG, and JPG files. Designed for hackathons and rapid deployment, it ensures no data leaves the user's environment.

---

## 🚀 Features

- **Multi-Format Support**: Processes digital PDFs, scanned PDFs, and raw images (PNG/JPG).
- **Intelligent PII Detection**: Uses high-precision regex patterns for Aadhaar, PAN, Phone, and Email.
- **Interactive Review**: Toggle redactions on a live preview with localized bounding boxes.
- **Stateless Architecture**: No database or session storage. Your files are re-processed on-demand and purged instantly.
- **Graceful Degradation**: Built-in "Mock Mode" (Ctrl+Shift+D) ensures the UI always performs, even without a backend.

---

## 🛠️ Technology Stack

- **Frontend**: React 18, Vite, Vanilla CSS (Glassmorphism & Modern Dark Mode).
- **Backend**: FastAPI (Python 3.12), `pdfplumber`, `PyMuPDF`, `pytesseract` (OCR).
- **Detection**: Deterministic Regex Engine (Zero-latency PII identification).

---

## 📦 Installation & Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (Add to PATH)

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

---

## 🎮 How to Use

1. **Upload**: Drag and drop a document onto the dashboard.
2. **Scan**: Wait for the AI-powered scan to identify sensitive fields.
3. **Review**: Check the sidebar for detected PII. Toggle individual items or "Mask All".
4. **Secure**: Click "Download Redacted PDF". The backend draws permanent black rectangles over the chosen fields and returns a new PDF.

> [!TIP]
> **Demo Mode**: If you are presenting and the OCR backend is unavailable, press `Ctrl + Shift + D` to trigger the "Force Demo Mode" with pre-loaded high-quality sample data.

---

## 🔒 Security & Privacy

- **0 Bytes Retained**: No files are stored on the server.
- **In-Memory Cache**: Bounding boxes are stored in a short-lived memory cache keyed by file hash, cleared automatically.
- **Client-Side Masks**: All PII display values are masked (`XXXX`) before leaving the backend.

---

## 📄 License
MIT License. Created for the Advanced Agentic Coding Hackathon.