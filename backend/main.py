from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
import os
import fitz  # PyMuPDF

from dotenv import load_dotenv
load_dotenv()

# --- Limites gratuites ---
FREE_PAGE_LIMIT = 30
FREE_WORD_LIMIT = 50_000

app = FastAPI(title="Smart PDF I-Gen Backend")

# --- CORS : origines autorisées (dev + front en prod) ---
# NB: on autorise le front Vercel et le dev local. Le domaine backend n'est pas requis pour CORS.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://smart-pdf-i-gen.vercel.app",
    # (facultatif) si tu as un autre front, ajoute-le ici
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,   # mets False si tu n'utilises pas de cookies/credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    """Health check route"""
    return {"pong": True, "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")}

@app.post("/api/summarize")
async def summarize_pdf(file: UploadFile = File(...)):
    """
    Réception d'un PDF, extraction du texte, puis double résumé :
      - simple_summarizer : heuristique rapide (3 phrases)
      - smart_groq_summary : appel Groq (LLM)
    """
    tmp_path = None
    doc = None

    try:
        # 1) Sauvegarde temporaire du PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        # 2) Extraction du texte
        doc = fitz.open(tmp_path)
        full_text_parts = []
        for page in doc:
            full_text_parts.append(page.get_text())
        nb_pages = doc.page_count
        full_text = " ".join(full_text_parts)
        nb_words = len(full_text.split())

        if not full_text.strip():
            return JSONResponse({"error": "The PDF is empty or unreadable."}, status_code=400)

        # 3) Paywall : limites gratuites
        if nb_pages > FREE_PAGE_LIMIT or nb_words > FREE_WORD_LIMIT:
            return JSONResponse(
                {
                    "error": "This document exceeds the free limit (30 pages or 50,000 words). Please subscribe to continue.",
                    "paywall": True,
                    "nb_pages": nb_pages,
                    "nb_words": nb_words,
                },
                status_code=402,  # 402 Payment Required
            )

        # 4) Résumés
        summary = simple_summarizer(full_text)
        ai_summary = smart_groq_summary(full_text)

        return {
            "summary": summary,
            "ai_summary": ai_summary,
            "nb_pages": nb_pages,
            "nb_words": nb_words,
            "paywall": False,
        }

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    finally:
        # Nettoyage (sécurité)
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
    """
    Petit résumé heuristique : prend les premières phrases du texte.
    """
    import re
    # Split en phrases multilingues (., !, ?, ponctuations asiatiques)
    sentences = re.split(r'(?<=[.!?。？])\s+', text.strip())
    return " ".join(sentences[:max_sentences])


def smart_groq_summary(text: str) -> str:
    """
    Appel à l'API Groq (endpoint OpenAI-compatible) pour un résumé structuré.
    - Utilise GROQ_API_KEY (obligatoire)
    - Utilise GROQ_MODEL (optionnel, défaut: llama-3.3-70b-versatile)
    - IMPORTANT (SDK OpenAI) : utiliser max_tokens, pas max_completion_tokens.
    """
    import openai

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # On tronque pour éviter d'envoyer des documents gigantesques en entrée
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
            base_url="https://api.groq.com/openai/v1",  # OpenAI-compatible
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at summarizing professional and academic documents in all languages.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,   # <- SDK OpenAI attend max_tokens
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    except Exception as e:
        return f"[Groq Error] {e}"
