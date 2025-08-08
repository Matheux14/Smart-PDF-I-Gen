from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import fitz  # PyMuPDF
import tempfile
import os

from dotenv import load_dotenv
load_dotenv()

# --- Limites gratuites ---
FREE_PAGE_LIMIT = 30
FREE_WORD_LIMIT = 50000

app = FastAPI()

# CORS config
origins = [
    "http://localhost:5173",              # Pour le dev local
    "https://smart-pdf-i-gen.vercel.app", # Ton déploiement Vercel (ou adapte)
    "https://summarizeai.com",
    "https://www.summarizeai.com",
    "https://smart-pdf-i-gen-1.onrender.com"
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
def ping():
    """Health check route"""
    return {"pong": True}

@app.post("/api/summarize")
async def summarize_pdf(file: UploadFile = File(...)):
    # 1. Save PDF temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Extract text
        doc = fitz.open(tmp_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        nb_pages = doc.page_count
        nb_words = len(full_text.split())
        doc.close()

        # Always remove the temp file (good cloud hygiene)
        os.remove(tmp_path)

        if not full_text.strip():
            return JSONResponse({"error": "The PDF is empty or unreadable."}, status_code=400)

        # Paywall: block if too large
        if nb_pages > FREE_PAGE_LIMIT or nb_words > FREE_WORD_LIMIT:
            return JSONResponse({
                "error": "This document exceeds the free limit (30 pages or 50,000 words). Please subscribe to continue.",
                "paywall": True,
                "nb_pages": nb_pages,
                "nb_words": nb_words
            }, status_code=402)  # 402 = Payment Required

        # Simple summary
        summary = simple_summarizer(full_text)

        # AI summary
        ai_summary = smart_groq_summary(full_text)

        return {
            "summary": summary,
            "ai_summary": ai_summary,
            "nb_pages": nb_pages,
            "nb_words": nb_words,
            "paywall": False
        }
    except Exception as e:
        # Try to remove the temp file in case of crash (double check)
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return JSONResponse({"error": str(e)}, status_code=500)

def simple_summarizer(text, max_sentences=3):
    import re
    # Split into sentences (multi-language)
    sentences = re.split(r'(?<=[.!?。؟]) +', text)
    summary = ' '.join(sentences[:max_sentences])
    return summary

def smart_groq_summary(text):
    import openai

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "[Groq Error] No API key defined"

    prompt = (
        "Summarize this PDF document in the original language, professionally, as if explaining to an executive. "
        "Extract only the key information, main results, recommendations, and important insights for decision-making. "
        "Use bullet or numbered lists for clarity.\n\n"
        "Expected structure:\n"
        "1. Executive summary (2-3 sentences)\n"
        "2. Key points / Results (list)\n"
        "3. Recommendations (list)\n"
        "4. Other important remarks (optional)\n\n"
        f"PDF content:\n{text[:6000]}"
    )

    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": "You are an expert at summarizing professional and academic documents in all languages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[Groq Error] {e}"
