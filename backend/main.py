from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import fitz  # PyMuPDF
import uuid

from dotenv import load_dotenv
load_dotenv()

# ------- Free limits -------
FREE_PAGE_LIMIT = int(os.getenv("FREE_PAGE_LIMIT", "30"))
FREE_WORD_LIMIT = int(os.getenv("FREE_WORD_LIMIT", "50000"))

# ------- Tokens (Render -> Environment) -------
ADMIN_BYPASS_TOKEN = os.getenv("ADMIN_BYPASS_TOKEN")
# PREMIUM_TOKENS: liste de tokens premium séparés par des virgules
PREMIUM_TOKENS = [t.strip() for t in os.getenv("PREMIUM_TOKENS", "").split(",") if t.strip()]

# ------- In-memory doc store (MVP) -------
# doc_id -> {"text": str, "pages": int, "words": int}
DOC_STORE = {}

app = FastAPI(title="Smart PDF I-Gen Backend")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://smart-pdf-i-gen.vercel.app",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # permet x-admin-token / x-premium-token
)

# ---------- Helpers ----------
def is_admin(request: Request) -> bool:
    if not ADMIN_BYPASS_TOKEN:
        return False
    return request.headers.get("x-admin-token", "") == ADMIN_BYPASS_TOKEN

def is_premium(request: Request) -> bool:
    tok = request.headers.get("x-premium-token", "")
    return bool(tok and tok in PREMIUM_TOKENS)

def extract_pdf_text_sorted(pdf_path: str) -> str:
    """Extraction robuste: blocs triés (y,x) + fallback + normalisation."""
    import unicodedata
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        blocks = page.get_text("blocks") or []
        # block = (x0, y0, x1, y1, text, block_no, ...)
        blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
        txt = "\n".join(b[4] for b in blocks if isinstance(b[4], str) and b[4].strip())
        if len((txt or "").strip()) < 40:  # fallback si page quasi vide
            txt = page.get_text("text")
        txt = unicodedata.normalize("NFKC", (txt or "")).replace("\x00", "")
        pages.append(txt)
    doc.close()
    return "\n\n".join(pages)

def tidy_text(s: str) -> str:
    """Nettoie artefacts: espaces, traits répétés, répétitions aberrantes, lignes vides."""
    import re, unicodedata
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u200b", "").replace("\x00", "")
    s = re.sub(r"[^\S\r\n]+", " ", s)               # espaces multiples -> 1
    s = re.sub(r"[-_]{4,}", "—", s)                 # longues suites de -/_
    s = re.sub(r"\b(\w{2,})(?:\W+\1){7,}\b", r"\1", s, flags=re.IGNORECASE)  # répétitions
    s = re.sub(r"\n{3,}", "\n\n", s)                # lignes vides multiples
    return s.strip()

def simple_summarizer(text: str, max_sentences: int = 3) -> str:
    import re
    sentences = re.split(r'(?<=[.!?。？])\s+', (text or "").strip())
    return " ".join(sentences[:max_sentences])

def smart_groq_summary(text: str) -> str:
    """Résumé IA via Groq (endpoint OpenAI-compatible)."""
    import openai
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    head = (text or "")[:6000]

    prompt = (
        "Summarize this PDF document in the original language, professionally, as if explaining to an executive. "
        "Extract only the key information, main results, recommendations, and important insights for decision-making. "
        "Use bullet or numbered lists for clarity.\n\n"
        "Expected structure:\n"
        "1. Executive summary (2-3 sentences)\n"
        "2. Key points / Results (list)\n"
        "3. Recommendations (list)\n"
        "4. Other important remarks (optional)\n\n"
        f"PDF content:\n{head}"
    )

    try:
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at summarizing professional and academic documents in all languages."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Groq Error] {e}"

def smart_groq_qa(context: str, question: str) -> str:
    """Q&A sur le document via Groq."""
    import openai
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    ctx = (context or "")[:7000]
    user = (
        "Answer the question strictly using the provided PDF context. "
        "Cite section names if they appear. Be concise and structured.\n\n"
        f"Question: {question}\n\n"
        f"PDF Context:\n{ctx}"
    )
    try:
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant for answering questions about a PDF."},
                {"role": "user", "content": user},
            ],
            max_tokens=500,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Groq Error] {e}"

# ---------- Health ----------
@app.get("/ping")
def ping():
    return {"pong": True, "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")}

# ---------- Auth check ----------
@app.get("/auth/check")
def auth_check(request: Request):
    return {"admin": is_admin(request)}

@app.get("/auth/premium/check")
def premium_check(request: Request):
    return {"premium": is_premium(request)}

# ---------- Summarize ----------
@app.post("/api/summarize")
async def summarize_pdf(request: Request, file: UploadFile = File(...)):
    """
    Upload PDF -> extract -> simple + AI summary.
    - Stocke le texte en mémoire et renvoie doc_id
    - Bypass paywall si admin OU premium
    """
    tmp_path = None
    doc = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Ouvrir juste pour compter les pages
        doc = fitz.open(tmp_path)
        nb_pages = doc.page_count
        doc.close()
        doc = None

        # Extraction robuste + nettoyage
        full_text = extract_pdf_text_sorted(tmp_path)
        full_text = tidy_text(full_text)
        nb_words = len(full_text.split())

        if not full_text.strip():
            return JSONResponse({"error": "The PDF is empty or unreadable."}, status_code=400)

        admin_ok = is_admin(request)
        premium_ok = is_premium(request)

        # Paywall si ni admin ni premium
        if (nb_pages > FREE_PAGE_LIMIT or nb_words > FREE_WORD_LIMIT) and not (admin_ok or premium_ok):
            return JSONResponse(
                {
                    "error": f"This document exceeds the free limit ({FREE_PAGE_LIMIT} pages or {FREE_WORD_LIMIT} words).",
                    "paywall": True,
                    "nb_pages": nb_pages,
                    "nb_words": nb_words,
                },
                status_code=402,
            )

        # Résumés
        summary = simple_summarizer(full_text)
        ai_summary = smart_groq_summary(full_text)

        # Store doc and return doc_id (for Q&A)
        doc_id = uuid.uuid4().hex
        DOC_STORE[doc_id] = {"text": full_text, "pages": nb_pages, "words": nb_words}

        return {
            "summary": summary,
            "ai_summary": ai_summary,
            "nb_pages": nb_pages,
            "nb_words": nb_words,
            "paywall": False,
            "admin_bypass": admin_ok,
            "premium": premium_ok,
            "doc_id": doc_id,
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        try:
            if doc is not None:
                doc.close()
        except Exception:
            pass
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

# ---------- Q&A ----------
@app.post("/api/ask")
async def ask_pdf(request: Request, payload: dict):
    """
    Q&A premium/admin:
    - headers: x-admin-token / x-premium-token
    - body: {"question": str, "doc_id": str (optionnel), "context_hint": str (optionnel)}
    """
    admin_ok = is_admin(request)
    premium_ok = is_premium(request)
    if not (admin_ok or premium_ok):
        return JSONResponse({"error": "Premium or admin required for Q&A."}, status_code=403)

    question = (payload.get("question") or "").strip()
    if not question:
        return JSONResponse({"error": "Missing 'question'."}, status_code=400)

    doc_id = (payload.get("doc_id") or "").strip()
    context_hint = (payload.get("context_hint") or "").strip()

    context = ""
    if doc_id and doc_id in DOC_STORE:
        context = DOC_STORE[doc_id]["text"]
    elif context_hint:
        context = context_hint

    if not context:
        return JSONResponse({"error": "No document context available."}, status_code=400)

    answer = smart_groq_qa(context, question)
    return {"answer": answer, "doc_id": doc_id or None}
