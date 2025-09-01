from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import fitz  # PyMuPDF

from dotenv import load_dotenv
load_dotenv()

# --- Limites gratuites via ENV (modifiable sur Render) ---
FREE_PAGE_LIMIT = int(os.getenv("FREE_PAGE_LIMIT", "30"))
FREE_WORD_LIMIT = int(os.getenv("FREE_WORD_LIMIT", "50000"))

# --- Admin bypass token (Render -> Environment) ---
ADMIN_BYPASS_TOKEN = os.getenv("ADMIN_BYPASS_TOKEN")

app = FastAPI(title="Smart PDF I-Gen Backend")

# --- CORS ---
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
    allow_headers=["*"],  # x-admin-token autorisé
)

@app.get("/ping")
def ping():
    return {"pong": True, "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")}

# --- Nouveau : endpoint de validation admin ---
@app.get("/auth/check")
def auth_check(request: Request):
    token = request.headers.get("x-admin-token")
    ok = bool(ADMIN_BYPASS_TOKEN) and (token == ADMIN_BYPASS_TOKEN)
    return {"admin": ok}

@app.post("/api/summarize")
async def summarize_pdf(request: Request, file: UploadFile = File(...)):
    """
    Upload PDF -> extract -> simple + AI summary.
    Admin bypass: si x-admin-token valide, ignore les limites gratuites.
    """
    tmp_path = None
    doc = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        doc = fitz.open(tmp_path)
        full_text_parts = [page.get_text() for page in doc]
        nb_pages = doc.page_count
        full_text = " ".join(full_text_parts)
        nb_words = len(full_text.split())

        if not full_text.strip():
            return JSONResponse({"error": "The PDF is empty or unreadable."}, status_code=400)

        # --- Admin bypass ---
        is_admin = bool(ADMIN_BYPASS_TOKEN) and (
            request.headers.get("x-admin-token") == ADMIN_BYPASS_TOKEN
        )

        # Paywall (s’applique seulement si pas admin)
        if (nb_pages > FREE_PAGE_LIMIT or nb_words > FREE_WORD_LIMIT) and not is_admin:
            return JSONResponse(
                {
                    "error": f"This document exceeds the free limit ({FREE_PAGE_LIMIT} pages or {FREE_WORD_LIMIT} words).",
                    "paywall": True,
                    "nb_pages": nb_pages,
                    "nb_words": nb_words,
                },
                status_code=402,
            )

        # Résumé simple
        summary = simple_summarizer(full_text)
        # Résumé IA
        ai_summary = smart_groq_summary(full_text)

        return {
            "summary": summary,
            "ai_summary": ai_summary,
            "nb_pages": nb_pages,
            "nb_words": nb_words,
            "paywall": False,
            "admin_bypass": is_admin,
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

# ------------------ Helpers ------------------

def simple_summarizer(text: str, max_sentences: int = 3) -> str:
    import re
    sentences = re.split(r'(?<=[.!?。？])\s+', text.strip())
    return " ".join(sentences[:max_sentences])

def smart_groq_summary(text: str) -> str:
    """
    Appel Groq via endpoint OpenAI-compatible.
    SDK OpenAI -> utiliser max_tokens.
    """
    import openai

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    head = text[:6000]

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
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at summarizing professional and academic documents in all languages."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,   # (SDK OpenAI)
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[Groq Error] {e}"
