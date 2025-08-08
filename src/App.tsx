import React, { useState, useRef } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import 'katex/dist/katex.min.css';
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
  Eye
} from "lucide-react";

// Example PDFs for demo carousel
const examplePdfs = [
  { name: "Research Paper", pages: 12, type: "Academic" },
  { name: "Business Report", pages: 8, type: "Corporate" },
  { name: "Technical Manual", pages: 25, type: "Technical" },
  { name: "Legal Document", pages: 15, type: "Legal" }
];

// --- UTILS ---
function parseSections(raw: string) {
  const regex = /\*\*(.+?)\*\*/g;
  let match;
  let lastIndex = 0;
  let sections: { title: string; content: string }[] = [];
  let currentTitle = "";
  while ((match = regex.exec(raw)) !== null) {
    if (sections.length > 0) {
      sections[sections.length - 1].content = raw.slice(lastIndex, match.index).trim();
    }
    currentTitle = match[1];
    sections.push({ title: currentTitle, content: "" });
    lastIndex = regex.lastIndex;
  }
  if (sections.length > 0) {
    sections[sections.length - 1].content = raw.slice(lastIndex).trim();
  }
  if (sections.length > 0 && raw.indexOf("**") > 0) {
    const header = raw.slice(0, raw.indexOf("**")).trim();
    if (header) sections.unshift({ title: "Header", content: header });
  }
  if (sections.length === 0) {
    return [{ title: "", content: raw }];
  }
  return sections;
}

const PAYWALL_PAGES = 30;
const PAYWALL_WORDS = 50000;
const KO_FI_LINK = "https://ko-fi.com/konanothniel155";

// Utilise l'URL d'API selon l'environnement
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- Drag & Drop events ---
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

  // --- File select ---
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setUploadedFile(files[0]);
      resetAll();
    }
  };
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  function resetAll() {
    setSummaryRaw("");
    setAiSummary("");
    setError("");
    setPaywall(false);
    setNbPages(null);
    setWordCount(0);
    setProcessingTime("");
  }

  // --- Upload & Summarize ---
  const handleSummarize = async () => {
    if (!uploadedFile) return;
    setIsProcessing(true);
    resetAll();

    try {
      const t0 = performance.now();
      const formData = new FormData();
      formData.append("file", uploadedFile);

      const res = await axios.post(
        `${API_URL}/api/summarize`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      const t1 = performance.now();

      setProcessingTime(((t1 - t0) / 1000).toFixed(1) + "s");
      setSummaryRaw(res.data.summary || "");
      setAiSummary(res.data.ai_summary || "");
      setWordCount(res.data.nb_words || 0);
      setNbPages(res.data.nb_pages || null);
      setPaywall(res.data.paywall || false);
    } catch (err: any) {
      const paywallResponse = err?.response?.data?.paywall;
      if (paywallResponse) {
        setPaywall(true);
        setNbPages(err?.response?.data?.nb_pages || null);
        setWordCount(err?.response?.data?.nb_words || 0);
        setError("");
      } else {
        setError(
          err?.response?.data?.error ||
          "PDF analysis failed. Please try again or use a smaller file."
        );
      }
    } finally {
      setIsProcessing(false);
    }
  };

  // --- Copy summary as plain text ---
  const copyToClipboard = () => {
    navigator.clipboard.writeText((aiSummary || summaryRaw).trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // --- Carousel example ---
  const nextExample = () =>
    setCurrentExample(prev => (prev + 1) % examplePdfs.length);
  const prevExample = () =>
    setCurrentExample(prev => (prev - 1 + examplePdfs.length) % examplePdfs.length);

  // --- Paywall UI (ENGLISH) ---
  const PaywallNotice = () => (
    <div className="bg-yellow-200 text-yellow-900 rounded-xl p-5 my-4 text-center shadow-lg border border-yellow-300">
      <h3 className="text-2xl font-bold mb-2">
        Large document detected
      </h3>
      <p className="mb-2">
        This document has <b>{nbPages}</b> pages ({wordCount} words).<br />
        The free limit is <b>{PAYWALL_PAGES} pages</b> or <b>{PAYWALL_WORDS} words</b>.
      </p>
      <p className="mb-4 font-semibold">
        <span className="text-red-700">
          Please support the project or unlock large document processing via Ko-fi (supports PayPal, Mobile Money, cards)!
        </span>
      </p>
      <div className="flex flex-col md:flex-row items-center justify-center gap-4">
        <a
          href={KO_FI_LINK}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block bg-pink-500 hover:bg-pink-700 text-white px-6 py-3 rounded-xl font-bold shadow transition"
        >
          💖 Support / Unlock with Ko-fi
        </a>
      </div>
      <p className="text-xs mt-4">
        After payment, contact us (WhatsApp, email, or Ko-fi) to activate your premium access.
      </p>
    </div>
  );

  // --- PREMIUM BANNER ---
  const PremiumBanner = () => (
    <div className="flex justify-center mt-2 mb-8">
      <div className="bg-gradient-to-r from-yellow-300 via-pink-200 to-blue-200 text-[#222a3b] rounded-2xl px-6 py-4 shadow-lg border border-yellow-400 max-w-2xl w-full text-center">
        <div className="flex flex-col md:flex-row items-center justify-center gap-3">
          <span className="text-xl font-semibold">
            🚀 Want unlimited large PDF summaries & AI-powered Q&#38;A?
          </span>
          <a
            href={KO_FI_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block bg-pink-500 hover:bg-pink-700 text-white px-5 py-2 rounded-xl font-bold shadow transition mt-2 md:mt-0"
          >
            💖 Upgrade Now via Ko-fi
          </a>
        </div>
        <div className="text-sm text-[#555] mt-2">
          Supporting us unlocks unlimited access to premium features and helps this project grow.
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#232E45] to-[#1C2030] text-white flex flex-col">
      {/* Header */}
      <header className="pt-12 pb-8 text-center">
        <div className="flex items-center justify-center mb-4">
          <div className="p-3 bg-gradient-to-r from-indigo-600 to-blue-600 rounded-xl mr-4">
            <Zap className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-5xl font-bold bg-gradient-to-r from-indigo-400 to-blue-400 text-transparent bg-clip-text">
            Smart-PDF-I-Gen
          </h1>
        </div>
        <p className="text-xl text-slate-300 max-w-2xl mx-auto leading-relaxed">
          Transform any PDF document into concise, intelligent summaries using advanced AI technology.
        </p>
      </header>

      {/* Premium Banner */}
      <PremiumBanner />

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto px-6 pb-16 w-full">
        <div className="grid lg:grid-cols-2 gap-8">
          {/* Left: Upload & Carousel */}
          <div className="bg-[#232840] rounded-2xl shadow-lg p-8 flex flex-col">
            <div className="flex items-center mb-6">
              <Upload className="w-6 h-6 text-indigo-400 mr-3" />
              <h2 className="text-2xl font-semibold text-white">Upload Your PDF</h2>
            </div>
            {/* Upload zone */}
            <div
              className={`p-8 text-center mb-6 border-2 border-dashed rounded-xl transition-colors ${
                isDragOver
                  ? "border-indigo-400 bg-[#1E2436]"
                  : "border-[#33498c] bg-[#232840]"
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
                <div className="space-y-4">
                  <FileCheck className="w-16 h-16 text-green-400 mx-auto" />
                  <div>
                    <p className="text-lg font-medium text-white">{uploadedFile.name}</p>
                    <p className="text-slate-400">
                      {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <FileText className="w-16 h-16 text-slate-400 mx-auto" />
                  <div>
                    <p className="text-lg font-medium text-white mb-2">
                      Drag & drop your PDF here
                    </p>
                    <p className="text-slate-400">or click to browse files</p>
                  </div>
                </div>
              )}
            </div>
            {/* Action button */}
            <button
              onClick={handleSummarize}
              disabled={!uploadedFile || isProcessing}
              className={`w-full py-3 rounded-xl font-bold shadow transition text-lg mt-2
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
            {/* Example PDFs Carousel */}
            <div className="mt-8">
              <h3 className="text-lg font-medium text-white mb-4">Example Documents</h3>
              <div className="bg-[#20253C] rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <button
                    onClick={prevExample}
                    className="p-2 hover:bg-slate-600/50 rounded-lg transition-colors"
                  >
                    <ChevronLeft className="w-5 h-5 text-slate-300" />
                  </button>
                  <div className="text-center flex-1">
                    <p className="font-medium text-white">
                      {examplePdfs[currentExample].name}
                    </p>
                    <p className="text-sm text-slate-400">
                      {examplePdfs[currentExample].pages} pages •{" "}
                      {examplePdfs[currentExample].type}
                    </p>
                  </div>
                  <button
                    onClick={nextExample}
                    className="p-2 hover:bg-slate-600/50 rounded-lg transition-colors"
                  >
                    <ChevronRight className="w-5 h-5 text-slate-300" />
                  </button>
                </div>
              </div>
            </div>
          </div>
          {/* Right: Summary Section */}
          <div className="bg-[#232840] rounded-2xl shadow-lg p-8 flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center">
                <FileText className="w-6 h-6 text-indigo-400 mr-3" />
                <h2 className="text-2xl font-semibold text-white">AI Summary</h2>
              </div>
              <div className="flex space-x-2 items-center">
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
                {copied && (
                  <span className="text-green-400 ml-2 transition-opacity duration-300">
                    Copied !
                  </span>
                )}
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
            {error && (
              <div className="bg-red-500 text-white p-2 rounded mb-4">{error}</div>
            )}
            {/* Paywall */}
            {paywall && <PaywallNotice />}
            {/* Summary: business-like/sectioned rendering */}
            {!paywall && (
              <div className="space-y-6 mb-6 max-h-[320px] overflow-y-auto px-2">
                {!aiSummary && !summaryRaw && !isProcessing && !error && (
                  <div className="text-slate-400 italic">
                    No summary yet. Upload a PDF to get started.
                  </div>
                )}
                {(aiSummary || summaryRaw) &&
                  parseSections(aiSummary || summaryRaw).map((section, idx) => (
                    <div
                      key={idx}
                      className={`rounded-xl shadow ${
                        section.title === "Header"
                          ? "bg-transparent text-base px-2 py-1"
                          : "bg-[#222a3b] p-4"
                      }`}
                    >
                      {section.title && section.title !== "Header" && (
                        <div className="font-bold text-lg mb-2 text-indigo-200">
                          {section.title}
                        </div>
                      )}
                      <div className="prose prose-invert max-w-none text-base">
                        <ReactMarkdown
                          remarkPlugins={[remarkMath]}
                          rehypePlugins={[rehypeKatex]}
                        >
                          {section.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                  ))}
              </div>
            )}
            {/* Controls/Stats */}
            <div className="space-y-6 mt-auto">
              <div className="grid grid-cols-3 gap-4">
                <div className="stat-item text-center">
                  <Clock className="w-5 h-5 text-indigo-400 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">Processing Time</p>
                  <p className="font-semibold text-white">
                    {processingTime || "--"}
                  </p>
                </div>
                <div className="stat-item text-center">
                  <FileText className="w-5 h-5 text-blue-400 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">Word Count</p>
                  <p className="font-semibold text-white">
                    {wordCount || "--"}
                  </p>
                </div>
                <div className="stat-item text-center">
                  <Eye className="w-5 h-5 text-green-400 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">Pages</p>
                  <p className="font-semibold text-white">
                    {nbPages !== null ? nbPages : "--"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
      {/* Footer */}
      <footer className="bg-[#232840] rounded-2xl mx-6 mb-6 p-6">
        <div className="flex flex-col md:flex-row items-center justify-between">
          <div className="text-center md:text-left mb-2 md:mb-0">
            <span className="text-lg font-semibold text-white">Smart PDF AI</span>
            <span className="mx-2 text-slate-400">|</span>
            <span className="text-slate-400">© {new Date().getFullYear()} summarizeai.com</span>
          </div>
          <div className="text-center md:text-right text-slate-400 text-sm">
            For support: <a href="mailto:support@summarizeai.com" className="underline hover:text-white">support@summarizeai.com</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;

// redeploy trigger