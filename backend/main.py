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
PREMIUM_TOKENS = [t.strip() for t in os.getenv("PREMIUM_TOKENS", "").split(",") if t.strip()]

# ------- In-memory doc store (MVP) -------
# doc_id -> {"text": str, "pages": int, "words": int, "chunks": [{"text": str, "norm": str}]}
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
    allow_headers=["*"],  # x-admin-token / x-premium-token
)

# ---------- Auth helpers ----------
def is_admin(request: Request) -> bool:
    if not ADMIN_BYPASS_TOKEN:
        return False
    return request.headers.get("x-admin-token", "") == ADMIN_BYPASS_TOKEN

def is_premium(request: Request) -> bool:
    tok = request.headers.get("x-premium-token", "")
    return bool(tok and tok in PREMIUM_TOKENS)

# ---------- Text helpers ----------
def extract_pdf_text_sorted(pdf_path: str) -> str:
    """Extraction robuste: blocs triés (y,x) + fallback + normalisation."""
    import unicodedata
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        blocks = page.get_text("blocks") or []
        blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))  # (y, x)
        txt = "\n".join(b[4] for b in blocks if isinstance(b[4], str) and b[4].strip())
        if len((txt or "").strip()) < 40:  # fallback si la page est quasi vide
            txt = page.get_text("text")
        txt = unicodedata.normalize("NFKC", (txt or "")).replace("\x00", "")
        pages.append(txt)
    doc.close()
    return "\n\n".join(pages)

def tidy_text(s: str) -> str:
    """Nettoie artefacts usuels."""
    import re, unicodedata
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u200b", "").replace("\x00", "")
    s = re.sub(r"[^\S\r\n]+", " ", s)               # espaces multiples -> 1
    s = re.sub(r"[-_]{4,}", "—", s)                 # longues suites de -/_ -> tiret cadratin
    s = re.sub(r"\b(\w{2,})(?:\W+\1){7,}\b", r"\1", s, flags=re.IGNORECASE)  # répétitions folles
    s = re.sub(r"\n{3,}", "\n\n", s)                # lignes vides multiples
    return s.strip()

def simple_summarizer(text: str, max_sentences: int = 3) -> str:
    import re
    sentences = re.split(r'(?<=[.!?。？])\s+', (text or "").strip())
    return " ".join(sentences[:max_sentences])

# ---------- Mini-RAG helpers ----------
def _normalize(s: str) -> str:
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

STOPWORDS = set("""
the a an and or of for to in into with without within over under than that this these those be is are was were been being
on at by from as if else but not no nor so such it its itself your you we our us i me my they them their themselves he she
him her his hers do does did done doing have has had having would could should may might can will just about around very
de la le les un une des du au aux et ou dans sur par pour sans sous plus que qui quoi dont où lorsque lorsqué ainsi donc
est sont était étaient être avoir avait avez avons avoirai
""".split())

def make_chunks(text: str, chunk_chars: int = 1200, overlap: int = 120):
    """Découpe par paragraphes, regroupe jusqu’à ~chunk_chars, overlap entre blocs."""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 <= chunk_chars:
            cur = f"{cur}\n{p}".strip()
        else:
            if cur:
                chunks.append(cur)
            # chevauchement simple
            cur_tail = cur[-overlap:] if cur else ""
            cur = (cur_tail + "\n" + p).strip()
    if cur:
        chunks.append(cur)
    # version normalisée
    return [{"text": c, "norm": _normalize(c)} for c in chunks]

def score_chunk(norm_chunk: str, norm_query: str) -> float:
    c_words = norm_chunk.split()
    q_words = [w for w in norm_query.split() if w not in STOPWORDS and len(w) > 2]
    if not q_words:
        return 0.0
    score = 0.0
    for w in q_words:
        score += c_words.count(w)
    # petit bonus si mot rare (long)
    score += sum(0.3 for w in q_words if len(w) >= 7 and w in norm_chunk)
    return score

def select_passages(text: str, question: str, k: int = 5, max_chars: int = 12000) -> str:
    chunks = make_chunks(text)
    qn = _normalize(question)
    ranked = sorted(
        chunks,
        key=lambda ch: score_chunk(ch["norm"], qn),
        reverse=True,
    )[: max(1, k)]
    ctx = "\n\n---\n\n".join(ch["text"] for ch in ranked)
    return ctx[:max_chars]

# ---------- LLM calls ----------
def smart_groq_summary(text: str) -> str:
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
    import openai
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    user = (
        "Using ONLY the provided PDF excerpts, answer the question accurately. "
        "Quote short snippets with “…” when useful and mention the section/page cues present in the excerpts if any. "
        "If the context does not contain the answer, say you cannot find it in the provided passages.\n\n"
        f"Question: {question}\n\n"
        f"PDF Excerpts:\n{context}"
    )
    try:
        client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a careful assistant that answers from given context only."},
                {"role": "user", "content": user},
            ],
            max_tokens=600,
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
    Upload PDF -> extract -> tidy -> simple + AI summary.
    - Stocke texte + chunks en mémoire (doc_id) pour le Q&A
    - Bypass paywall si admin OU premium
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Compte pages
        doc = fitz.open(tmp_path)
        nb_pages = doc.page_count
        doc.close()

        # Extraction robuste + nettoyage
        raw_text = extract_pdf_text_sorted(tmp_path)
        full_text = tidy_text(raw_text)
        nb_words = len(full_text.split())

        if not full_text.strip():
            return JSONResponse({"error": "The PDF is empty or unreadable."}, status_code=400)

        admin_ok = is_admin(request)
        premium_ok = is_premium(request)

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

        # Stockage + chunks pour RAG
        doc_id = uuid.uuid4().hex
        DOC_STORE[doc_id] = {
            "text": full_text,
            "pages": nb_pages,
            "words": nb_words,
            "chunks": make_chunks(full_text),
        }

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
        # Récupère les meilleurs passages du doc en mémoire
        context = select_passages(DOC_STORE[doc_id]["text"], question, k=6, max_chars=12000)
    elif context_hint:
        context = context_hint

    if not context:
        return JSONResponse({"error": "No document context available."}, status_code=400)

    answer = smart_groq_qa(context, question)
    return {"answer": answer, "doc_id": doc_id or None}
