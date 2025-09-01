from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import fitz  # PyMuPDF
import uuid
import json
import re
from difflib import SequenceMatcher
import hashlib
from time import time

from dotenv import load_dotenv
load_dotenv()

# ------- Free limits -------
FREE_PAGE_LIMIT = int(os.getenv("FREE_PAGE_LIMIT", "30"))
FREE_WORD_LIMIT = int(os.getenv("FREE_WORD_LIMIT", "50000"))

# ------- Tokens (Render -> Environment) -------
ADMIN_BYPASS_TOKEN = os.getenv("ADMIN_BYPASS_TOKEN")
PREMIUM_TOKENS = [t.strip() for t in os.getenv("PREMIUM_TOKENS", "").split(",") if t.strip()]

# ------- In-memory stores (MVP) -------
# doc_id -> {"text": str, "pages": int, "words": int, "chunks": [{"text": str, "norm": str}]}
DOC_STORE = {}
# caching (7 days TTL)
SUMMARY_CACHE = {}  # key: doc_hash -> {"md": str, "ts": float}
QA_CACHE = {}       # key: (doc_id, normalized_q) -> {"answer": str, "ts": float}

def _doc_hash(s: str) -> str:
    return hashlib.sha256((s or "")[:20000].encode("utf-8", "ignore")).hexdigest()

def _norm_q(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

app = FastAPI(title="Smart PDF I-Gen Backend")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://smart-pdf-i-gen.vercel.app",
    "https://smart-pdf-i-gen-1.onrender.com",  # utile pour tests directs
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
        if len((txt or "").strip()) < 40:
            txt = page.get_text("text")
        txt = unicodedata.normalize("NFKC", (txt or "")).replace("\x00", "")
        pages.append(txt)
    doc.close()
    return "\n\n".join(pages)

def tidy_text(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u200b", "").replace("\x00", "")
    s = re.sub(r"[^\S\r\n]+", " ", s)
    s = re.sub(r"[-_]{4,}", "—", s)
    s = re.sub(r"\b(\w{2,})(?:\W+\1){7,}\b", r"\1", s, flags=re.IGNORECASE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def simple_summarizer(text: str, max_sentences: int = 3) -> str:
    sentences = re.split(r'(?<=[.!?。？])\s+', (text or "").strip())
    return " ".join(sentences[:max_sentences])

# ---------- Mini-RAG helpers ----------
def _normalize(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

STOPWORDS = set("""
the a an and or of for to in into with without within over under than that this these those be is are was were been being
on at by from as if else but not no nor so such it its itself your you we our us i me my they them their themselves he she
him her his hers do does did done doing have has had having would could should may might can will just about around very
de la le les un une des du au aux et ou dans sur par pour sans sous plus que qui quoi dont ou où lorsque ainsi donc
est sont etait etaient etre avoir avait avez avons
""".split())

def make_chunks(text: str, chunk_chars: int = 1000, overlap: int = 100):
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 <= chunk_chars:
            cur = f"{cur}\n{p}".strip()
        else:
            if cur:
                chunks.append(cur)
            tail = cur[-overlap:] if cur else ""
            cur = (tail + "\n" + p).strip()
    if cur:
        chunks.append(cur)
    return [{"text": c, "norm": _normalize(c)} for c in chunks]

def _fuzzy_hit(word: str, token: str) -> bool:
    if abs(len(word) - len(token)) > 2:
        return False
    return SequenceMatcher(None, word, token).ratio() >= 0.84

def score_chunk(norm_chunk: str, norm_query: str) -> float:
    c_tokens = norm_chunk.split()
    q_tokens = [w for w in norm_query.split() if w not in STOPWORDS and len(w) > 2]
    if not q_tokens:
        return 0.0
    score = 0.0
    for w in q_tokens:
        exact = c_tokens.count(w)
        if exact:
            score += exact * 1.0
        else:
            # fuzzy boost (ex: "euler" vs "eulet" OCR)
            if any(_fuzzy_hit(w, t) for t in c_tokens):
                score += 0.7
    for w in q_tokens:
        if len(w) >= 7 and w in norm_chunk:
            score += 0.3
    return score

def select_passages(text: str, question: str, k: int = 6, max_chars: int = 10000) -> str:
    chunks = make_chunks(text, chunk_chars=1000, overlap=100)
    qn = _normalize(question)
    ranked = sorted(chunks, key=lambda ch: score_chunk(ch["norm"], qn), reverse=True)[:max(1, k)]
    ctx = "\n\n---\n\n".join(ch["text"] for ch in ranked)
    return ctx[:max_chars]

# ---------- Groq chat with fallback ----------
def _groq_chat(messages, max_tokens, temperature=0.2, model=None):
    import openai
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("No GROQ_API_KEY")
    client = openai.OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

    primary = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    fallback = os.getenv("GROQ_MODEL_FALLBACK", "").strip()
    tried = []

    last_err = None
    for m in [primary] + ([fallback] if fallback and fallback != primary else []):
        tried.append(m)
        try:
            return client.chat.completions.create(
                model=m,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as e:
            s = str(e).lower()
            last_err = e
            # auto-fallback on 429 / rate limit
            if "rate limit" in s or "429" in s or "limit" in s:
                continue
            # other errors → stop
            break
    raise RuntimeError(f"Groq call failed (tried {tried}): {last_err}")

# ---------- LLM calls ----------
def smart_groq_summary_structured(text: str):
    """
    Demande une sortie JSON stricte; fallback en markdown si parsing échoue.
    Renvoie (markdown_stable, sections_dict|None)
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined", None

    head = (text or "")[:4500]  # plus compact
    sys = (
        "You are an expert summarizer. Respond ONLY with a valid JSON object and nothing else. "
        'Schema: {"executive_summary": "2-3 sentences", "key_points": ["..."], '
        '"recommendations": ["..."], "remarks": "optional string"}'
    )
    user = (
        "Summarize the PDF content (same language) for an executive. Be concise and professional. "
        "Use short bullet items in arrays. No markdown, ONLY JSON.\n\n"
        f"PDF content:\n{head}"
    )
    try:
        resp = _groq_chat(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=450,
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.strip("` \n")
        if raw.startswith("json"):
            raw = raw[4:].strip()
        data = json.loads(raw)

        md = []
        if data.get("executive_summary"):
            md.append("**Executive summary (2–3 sentences)**\n\n" + data["executive_summary"].strip())
        if data.get("key_points"):
            md.append("**Key points / Results**\n\n" + "\n".join(f"- {x}" for x in data["key_points"]))
        if data.get("recommendations"):
            md.append("**Recommendations**\n\n" + "\n".join(f"- {x}" for x in data["recommendations"]))
        if data.get("remarks"):
            md.append("**Other important remarks**\n\n" + data["remarks"].strip())
        return "\n\n".join(md).strip(), data
    except Exception:
        # Fallback: markdown libre
        return smart_groq_summary_fallback(text), None

def smart_groq_summary_fallback(text: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"
    head = (text or "")[:3800]  # compact
    prompt = (
        "Summarize this PDF document in the original language, professionally, as if explaining to an executive. "
        "Extract only the key information, main results, recommendations, and important insights for decision-making. "
        "Use explicit bold section titles exactly like these and keep them in this order:\n"
        "**Executive summary (2–3 sentences)**, **Key points / Results**, **Recommendations**, **Other important remarks**.\n\n"
        f"PDF content:\n{head}"
    )
    try:
        resp = _groq_chat(
            messages=[
                {"role": "system", "content": "You are an expert at summarizing professional and academic documents in all languages."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=420,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Groq Error] {e}"

def smart_groq_qa(context: str, question: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"

    user = (
        "Using ONLY the provided PDF excerpts, answer the question accurately. "
        "Quote very short snippets with “…” and mention any visible page/section cues if present. "
        "If the answer is not in the excerpts, say you cannot find it in the provided passages.\n\n"
        f"Question: {question}\n\n"
        f"PDF Excerpts:\n{context}"
    )
    try:
        resp = _groq_chat(
            messages=[
                {"role": "system", "content": "You are a careful assistant that answers from given context only."},
                {"role": "user", "content": user},
            ],
            max_tokens=350,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Groq Error] {e}"

# ---------- Health ----------
@app.get("/ping")
def ping():
    return {
        "pong": True,
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "fallback": os.getenv("GROQ_MODEL_FALLBACK", ""),
    }

# ---------- Auth ----------
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
    Upload PDF -> extract -> tidy -> JSON-structured summary (fallback markdown).
    Stocke texte + chunks pour Q&A. Résumé mis en cache 7 jours par document.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # Compter pages
        doc = fitz.open(tmp_path)
        nb_pages = doc.page_count
        doc.close()

        # Texte nettoyé
        raw_text = extract_pdf_text_sorted(tmp_path)
        full_text = tidy_text(raw_text)
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

        # Caching du résumé (par contenu)
        dh = _doc_hash(full_text)
        cached = SUMMARY_CACHE.get(dh)
        if cached and (time() - cached["ts"] < 7 * 24 * 3600):
            ai_md, ai_sections = cached["md"], None
        else:
            ai_md, ai_sections = smart_groq_summary_structured(full_text)
            SUMMARY_CACHE[dh] = {"md": ai_md, "ts": time()}

        # Petit résumé heuristique
        simple = simple_summarizer(full_text)

        # Stockage + chunks pour Q&A
        doc_id = uuid.uuid4().hex
        DOC_STORE[doc_id] = {
            "text": full_text,
            "pages": nb_pages,
            "words": nb_words,
            "chunks": make_chunks(full_text),
        }

        return {
            "summary": simple,
            "ai_summary": ai_md,          # markdown stable
            "ai_sections": ai_sections,   # (optionnel) JSON structuré
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
    headers: x-admin-token / x-premium-token
    body: {"question": str, "doc_id": str (optionnel), "context_hint": str (optionnel)}
    - Sélection de passages compacte
    - Cache Q&A 7 jours par (doc_id, question)
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

    # Cache par (doc, question)
    cache_key = None
    if doc_id and doc_id in DOC_STORE:
        cache_key = (doc_id, _norm_q(question))
        hit = QA_CACHE.get(cache_key)
        if hit and (time() - hit["ts"] < 7 * 24 * 3600):
            return {"answer": hit["answer"], "doc_id": doc_id}

    # Contexte
    context = ""
    if doc_id and doc_id in DOC_STORE:
        context = select_passages(DOC_STORE[doc_id]["text"], question, k=6, max_chars=10000)
    elif context_hint:
        context = context_hint

    if not context:
        return JSONResponse({"error": "No document context available."}, status_code=400)

    answer = smart_groq_qa(context, question)

    # Mise en cache si succès
    if cache_key and isinstance(answer, str) and not answer.startswith("[Groq Error]"):
        QA_CACHE[cache_key] = {"answer": answer, "ts": time()}

    return {"answer": answer, "doc_id": doc_id or None}
