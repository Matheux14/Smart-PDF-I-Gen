import React, { useState, useRef, useEffect } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import {
  Upload,
  FileText,
  Copy,
  RefreshCw,
  Clock,
  FileCheck,
  ChevronLeft,
  ChevronRight,
  Zap,
  Eye,
  ShieldCheck,
} from "lucide-react";

/* =========================
   Demo carousel
========================= */
const examplePdfs = [
  { name: "Research Paper", pages: 12, type: "Academic" },
  { name: "Business Report", pages: 8, type: "Corporate" },
  { name: "Technical Manual", pages: 25, type: "Technical" },
  { name: "Legal Document", pages: 15, type: "Legal" },
];

/* =========================
   Utils
========================= */
function parseSections(raw: string) {
  const regex = /\*\*(.+?)\*\*/g;
  let match;
  let lastIndex = 0;
  const sections: { title: string; content: string }[] = [];
  while ((match = regex.exec(raw)) !== null) {
    if (sections.length > 0) {
      sections[sections.length - 1].content = raw.slice(lastIndex, match.index).trim();
    }
    sections.push({ title: match[1], content: "" });
    lastIndex = regex.lastIndex;
  }
  if (sections.length > 0) {
    sections[sections.length - 1].content = raw.slice(lastIndex).trim();
  }
  if (sections.length === 0) return [{ title: "", content: raw }];
  return sections;
}

/* =========================
   Constants (client)
========================= */
const PAYWALL_PAGES = 30;
const PAYWALL_WORDS = 50000;
const KO_FI_LINK = "https://ko-fi.com/konanothniel155";

// IMPORTANT : même clé d'env que côté déploiement
const API_URL =
  import.meta.env.VITE_API_BASE_URL || "https://smart-pdf-i-gen-1.onrender.com";

/* =========================
   Helpers
========================= */
// Validation côté serveur du token admin
async function validateAdmin(): Promise<boolean> {
  const token = localStorage.getItem("ADMIN_BYPASS_TOKEN");
  if (!token) return false;
  try {
    const r = await axios.get(`${API_URL}/auth/check`, {
      headers: { "x-admin-token": token },
    });
    return !!r.data?.admin;
  } catch {
    return false;
  }
}

/* =========================
   Component
========================= */
const App: React.FC = () => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentExample, setCurrentExample] = useState(0);

  const [summaryRaw, setSummaryRaw] = useState<string>("");
  const [aiSummary, setAiSummary] = useState<string>("");
  const [processingTime, setProcessingTime] = useState<string>("");
  const [wordCount, setWordCount] = useState<number>(0);
  const [nbPages, setNbPages] = useState<number | null>(null);
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [paywall, setPaywall] = useState(false);

  // Admin (validé par le serveur)
  const [adminOn, setAdminOn] = useState<boolean>(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Au chargement, on demande au serveur si le token local est valide
    validateAdmin().then(setAdminOn);
  }, []);

  /* ---------- Drag & Drop ---------- */
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type === "application/pdf") {
      setUploadedFile(files[0]);
      resetAll();
    }
  };

  /* ---------- File select ---------- */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setUploadedFile(files[0]);
      resetAll();
    }
  };
  const handleUploadClick = () => fileInputRef.current?.click();

  function resetAll() {
    setSummaryRaw("");
    setAiSummary("");
    setError("");
    setPaywall(false);
    setNbPages(null);
    setWordCount(0);
    setProcessingTime("");
  }

  /* ---------- Upload & Summarize ---------- */
  const handleSummarize = async () => {
    if (!uploadedFile) return;
    setIsProcessing(true);
    setError("");
    setPaywall(false);

    try {
      const t0 = performance.now();
      const formData = new FormData();
      formData.append("file", uploadedFile);

      // Header admin si présent
      const headers: Record<string, string> = { "Content-Type": "multipart/form-data" };
      const token = localStorage.getItem("ADMIN_BYPASS_TOKEN");
      if (token) headers["x-admin-token"] = token;

      const res = await axios.post(`${API_URL}/api/summarize`, formData, { headers });
      const t1 = performance.now();

      setProcessingTime(((t1 - t0) / 1000).toFixed(1) + "s");
      setSummaryRaw(res.data.summary || "");
      setAiSummary(res.data.ai_summary || "");
      setWordCount(res.data.nb_words || 0);
      setNbPages(res.data.nb_pages ?? null);
      setPaywall(!!res.data.paywall);
    } catch (err: any) {
      const paywallResponse = err?.response?.data?.paywall;
      if (paywallResponse) {
        setPaywall(true);
        setNbPages(err?.response?.data?.nb_pages ?? null);
        setWordCount(err?.response?.data?.nb_words ?? 0);
        setError("");
      } else {
        setError(
          err?.response?.data?.error || "PDF analysis failed. Please try again or use a smaller file."
        );
      }
    } finally {
      setIsProcessing(false);
    }
  };

  /* ---------- Copy ---------- */
  const copyToClipboard = () => {
    const text = (aiSummary || summaryRaw || "").trim();
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  /* ---------- Carousel ---------- */
  const nextExample = () => setCurrentExample((p) => (p + 1) % examplePdfs.length);
  const prevExample = () =>
    setCurrentExample((p) => (p - 1 + examplePdfs.length) % examplePdfs.length);

  /* ---------- Responsive Ko-fi banner ---------- */
  const PremiumBanner = () => (
    <div className="px-4 sm:px-6 lg:px-8 -mt-2 mb-8">
      <section
        className="
          w-full max-w-4xl mx-auto
          rounded-2xl border border-white/10
          bg-gradient-to-br from-fuchsia-500/10 via-indigo-500/10 to-cyan-400/10
          p-4 sm:p-5 lg:p-6 shadow-[0_6px_24px_rgba(0,0,0,.25)]
          flex flex-wrap items-center gap-3 sm:gap-4
        "
        role="complementary"
        aria-label="Premium upsell"
      >
        <div className="flex items-start gap-3 flex-1 min-w-[220px]">
          <span className="text-xl sm:text-2xl" aria-hidden>
            🚀
          </span>
          <div>
            <h3 className="m-0 font-bold text-base sm:text-lg text-white">
              Want unlimited large PDF summaries & AI-powered Q&A?
            </h3>
            <p className="m-0 mt-1 text-xs sm:text-sm text-slate-300">
              Supporting us unlocks premium features and helps this project grow.
            </p>
          </div>
        </div>

        <a
          href={KO_FI_LINK}
          target="_blank"
          rel="noreferrer"
          className="
            inline-flex items-center justify-center
            px-4 sm:px-5 py-2 rounded-xl font-bold
            bg-pink-400 text-slate-900
            hover:bg-pink-300 transition
            shadow-[0_10px_24px_rgba(255,80,170,.25)]
          "
          aria-label="Upgrade via Ko-fi"
        >
          💖 Upgrade via Ko-fi
        </a>
      </section>
    </div>
  );

  /* ---------- Paywall block ---------- */
  const PaywallNotice = () => (
    <div className="bg-yellow-200 text-yellow-900 rounded-xl p-5 my-4 text-center shadow-lg border border-yellow-300">
      <h3 className="text-2xl font-bold mb-2">Large document detected</h3>
      <p className="mb-2">
        This document has <b>{nbPages}</b> pages ({wordCount} words).<br />
        The free limit is <b>{PAYWALL_PAGES} pages</b> or <b>{PAYWALL_WORDS} words</b>.
      </p>
      <p className="mb-4 font-semibold">
        <span className="text-red-700">
          Please support the project or unlock large document processing via Ko-fi (PayPal, Mobile
          Money, cards).
        </span>
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
        <a
          href={KO_FI_LINK}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block bg-pink-500 hover:bg-pink-600 text-white px-6 py-3 rounded-xl font-bold shadow transition"
        >
          💖 Support / Unlock with Ko-fi
        </a>
      </div>
      <p className="text-xs mt-4">
        After payment, contact us (WhatsApp, email, or Ko-fi) to activate your premium access.
      </p>
    </div>
  );

  /* ---------- Admin pill ---------- */
  const AdminPill = () => (
    <button
      onClick={async () => {
        if (adminOn) {
          localStorage.removeItem("ADMIN_BYPASS_TOKEN");
          setAdminOn(false);
        } else {
          const t = prompt("Enter admin token (matches ADMIN_BYPASS_TOKEN on Render)");
          if (t && t.trim()) {
            localStorage.setItem("ADMIN_BYPASS_TOKEN", t.trim());
            const ok = await validateAdmin();
            setAdminOn(ok);
            if (!ok) alert("Invalid token.");
          }
        }
      }}
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-semibold
        ${adminOn ? "border-emerald-400/40 text-emerald-300 bg-emerald-600/10" : "border-white/15 text-slate-300 bg-white/5"}
      `}
      title="Toggle admin bypass"
    >
      <ShieldCheck className="w-4 h-4" />
      Admin: {adminOn ? "ON" : "OFF"}
    </button>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#232E45] to-[#1C2030] text-white flex flex-col">
      {/* Header */}
      <header className="pt-10 pb-6">
        <div className="max-w-7xl px-6 mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-gradient-to-r from-indigo-600 to-blue-600 rounded-xl">
              <Zap className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold bg-gradient-to-r from-indigo-400 to-blue-400 text-transparent bg-clip-text">
                Smart-PDF-I-Gen
              </h1>
              <p className="text-sm sm:text-base text-slate-300">
                Transform any PDF into concise, intelligent summaries using advanced AI.
              </p>
            </div>
          </div>

          {/* Admin switch (discret) */}
          <AdminPill />
        </div>
      </header>

      {/* Premium Banner — masquée pour l'admin validé */}
      {!adminOn && <PremiumBanner />}

      {/* Main */}
      <main className="flex-1 max-w-7xl mx-auto px-6 pb-16 w-full">
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Left: Upload */}
          <div className="bg-[#232840] rounded-2xl shadow-lg p-6 sm:p-8 flex flex-col">
            <div className="flex items-center mb-6">
              <Upload className="w-6 h-6 text-indigo-400 mr-3" />
              <h2 className="text-2xl font-semibold text-white">Upload Your PDF</h2>
            </div>

            {/* Dropzone */}
            <div
              className={`p-8 text-center mb-6 border-2 border-dashed rounded-xl transition-colors ${
                isDragOver ? "border-indigo-400 bg-[#1E2436]" : "border-[#33498c] bg-[#232840]"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={handleUploadClick}
              style={{ cursor: "pointer" }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                onChange={handleFileSelect}
                className="hidden"
              />
              {uploadedFile ? (
                <div className="space-y-3">
                  <FileCheck className="w-16 h-16 text-green-400 mx-auto" />
                  <div>
                    <p className="text-lg font-medium text-white break-all">{uploadedFile.name}</p>
                    <p className="text-slate-400">
                      {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <FileText className="w-16 h-16 text-slate-400 mx-auto" />
                  <div>
                    <p className="text-lg font-medium text-white mb-1">Drag & drop your PDF here</p>
                    <p className="text-slate-400">or click to browse files</p>
                  </div>
                </div>
              )}
            </div>

            {/* Action */}
            <button
              onClick={handleSummarize}
              disabled={!uploadedFile || isProcessing}
              className={`w-full py-3 rounded-xl font-bold shadow transition text-lg mt-1
                ${
                  !uploadedFile || isProcessing
                    ? "bg-indigo-900/60 text-[#b7cbfa] cursor-not-allowed"
                    : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-indigo-700 hover:to-blue-700 text-white"
                }`}
            >
              {isProcessing ? (
                <div className="flex items-center justify-center">
                  <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
                  Processing...
                </div>
              ) : (
                <div className="flex items-center justify-center">
                  <Zap className="w-5 h-5 mr-2" />
                  Upload & Summarize
                </div>
              )}
            </button>

            {/* Examples */}
            <div className="mt-8">
              <h3 className="text-lg font-medium text-white mb-4">Example Documents</h3>
              <div className="bg-[#20253C] rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <button
                    onClick={prevExample}
                    className="p-2 hover:bg-slate-600/50 rounded-lg transition-colors"
                    aria-label="Previous example"
                  >
                    <ChevronLeft className="w-5 h-5 text-slate-300" />
                  </button>
                  <div className="text-center flex-1">
                    <p className="font-medium text-white">{examplePdfs[currentExample].name}</p>
                    <p className="text-sm text-slate-400">
                      {examplePdfs[currentExample].pages} pages • {examplePdfs[currentExample].type}
                    </p>
                  </div>
                  <button
                    onClick={nextExample}
                    className="p-2 hover:bg-slate-600/50 rounded-lg transition-colors"
                    aria-label="Next example"
                  >
                    <ChevronRight className="w-5 h-5 text-slate-300" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Summary */}
          <div className="bg-[#232840] rounded-2xl shadow-lg p-6 sm:p-8 flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center">
                <FileText className="w-6 h-6 text-indigo-400 mr-3" />
                <h2 className="text-2xl font-semibold text-white">AI Summary</h2>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={copyToClipboard}
                  className={`p-2 bg-[#283353] hover:bg-[#314066] rounded-lg ${
                    !(aiSummary || summaryRaw) ? "opacity-50 cursor-not-allowed" : ""
                  }`}
                  title="Copy to clipboard"
                  disabled={!(aiSummary || summaryRaw)}
                >
                  <Copy className="w-4 h-4" />
                </button>
                {copied && <span className="text-green-400 text-sm">Copied!</span>}
                <button
                  onClick={() => {
                    setSummaryRaw("");
                    setAiSummary("");
                    setUploadedFile(null);
                    setError("");
                    setPaywall(false);
                    setNbPages(null);
                    setWordCount(0);
                    setProcessingTime("");
                  }}
                  className="p-2 bg-[#283353] hover:bg-[#314066] rounded-lg"
                  title="Refresh"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Error */}
            {error && <div className="bg-red-500/90 text-white p-3 rounded mb-4">{error}</div>}

            {/* Paywall — masqué pour l'admin validé */}
            {paywall && !adminOn && <PaywallNotice />}

            {/* Summary */}
            {!paywall && (
              <div className="space-y-6 mb-6 max-h-[320px] overflow-y-auto px-1 sm:px-2">
                {!aiSummary && !summaryRaw && !isProcessing && !error && (
                  <div className="text-slate-400 italic">No summary yet. Upload a PDF to start.</div>
                )}
                {(aiSummary || summaryRaw) &&
                  parseSections(aiSummary || summaryRaw).map((section, idx) => (
                    <div
                      key={idx}
                      className={`rounded-xl shadow ${
                        section.title ? "bg-[#222a3b] p-4" : "bg-transparent text-base px-2 py-1"
                      }`}
                    >
                      {section.title && (
                        <div className="font-bold text-lg mb-2 text-indigo-200">{section.title}</div>
                      )}
                      <div className="prose prose-invert max-w-none text-base">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {section.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 mt-auto">
              <div className="text-center">
                <Clock className="w-5 h-5 text-indigo-400 mx-auto mb-2" />
                <p className="text-sm text-slate-400">Processing Time</p>
                <p className="font-semibold text-white">{processingTime || "--"}</p>
              </div>
              <div className="text-center">
                <FileText className="w-5 h-5 text-blue-400 mx-auto mb-2" />
                <p className="text-sm text-slate-400">Word Count</p>
                <p className="font-semibold text-white">{wordCount || "--"}</p>
              </div>
              <div className="text-center">
                <Eye className="w-5 h-5 text-green-400 mx-auto mb-2" />
                <p className="text-sm text-slate-400">Pages</p>
                <p className="font-semibold text-white">{nbPages !== null ? nbPages : "--"}</p>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-[#232840] rounded-2xl mx-6 mb-6 p-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="text-center md:text-left">
            <span className="text-lg font-semibold text-white">Smart PDF AI</span>
            <span className="mx-2 text-slate-400">|</span>
            <span className="text-slate-400">© {new Date().getFullYear()} summarizeai.com</span>
          </div>
          <div className="text-center md:text-right text-slate-400 text-sm">
            For support:{" "}
            <a href="mailto:support@summarizeai.com" className="underline hover:text-white">
              support@summarizeai.com
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;

// redeploy trigger
