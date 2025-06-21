import React, { useState, useRef } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import {
  Upload,
  FileText,
  Copy,
  RefreshCw,
  Clock,
  FileCheck,
  Github,
  Linkedin,
  ChevronLeft,
  ChevronRight,
  Zap,
  Eye
} from "lucide-react";

// Exemple de PDF pour la démo carousel (inchangé)
const examplePdfs = [
  { name: "Research Paper", pages: 12, type: "Academic" },
  { name: "Business Report", pages: 8, type: "Corporate" },
  { name: "Technical Manual", pages: 25, type: "Technical" },
  { name: "Legal Document", pages: 15, type: "Legal" }
];


// --- UTILS ---

// Parse les sections markdown du résumé AI
function parseSections(raw: string) {
  // Sépare chaque section commençant par "**Titre**"
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
  // Ajoute le header (avant le premier titre markdown)
  if (sections.length > 0 && raw.indexOf("**") > 0) {
    const header = raw.slice(0, raw.indexOf("**")).trim();
    if (header) sections.unshift({ title: "Header", content: header });
  }
  // S'il n'y a aucune section, tout afficher dans une seule
  if (sections.length === 0) {
    return [{ title: "", content: raw }];
  }
  return sections;
}

const App: React.FC = () => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentExample, setCurrentExample] = useState(0);

  const [summaryRaw, setSummaryRaw] = useState<string>("");
  const [processingTime, setProcessingTime] = useState<string>("");
  const [wordCount, setWordCount] = useState<number>(0);
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // --- File to base64 ---
  const fileToBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        const base64 = (reader.result as string).split(",")[1];
        resolve(base64);
      };
      reader.onerror = reject;
    });

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
      setSummaryRaw("");
      setError("");
    }
  };

  // --- File select ---
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      setUploadedFile(files[0]);
      setSummaryRaw("");
      setError("");
    }
  };
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // --- Upload & Summarize ---
  const handleSummarize = async () => {
    if (!uploadedFile) return;
    setIsProcessing(true);
    setError("");
    setSummaryRaw("");
    setProcessingTime("");
    setWordCount(0);

    try {
      const base64 = await fileToBase64(uploadedFile);
      const t0 = performance.now();

      const res = await axios.post(
        "https://yyqocvqwpk.execute-api.us-east-1.amazonaws.com/Prod/analyze-pdf/",
        base64,
        { headers: { "Content-Type": "text/plain" } }
      );

      const t1 = performance.now();
      const summaryText: string = res.data.ai_summary || res.data.summary || res.data || "";
      setProcessingTime(((t1 - t0) / 1000).toFixed(1) + "s");
      setSummaryRaw(summaryText);

      setWordCount(
        summaryText.replace(/[*•✓\n\-]/g, "").split(/\s+/).filter(Boolean).length
      );
    } catch (err: any) {
      setError(
        err?.response?.data?.error ||
          "PDF analysis failed. Please try again or use a smaller file."
      );
    } finally {
      setIsProcessing(false);
    }
  };

  // --- Copy summary as plain text ---
  const copyToClipboard = () => {
    navigator.clipboard.writeText(summaryRaw.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // --- Carousel example ---
  const nextExample = () =>
    setCurrentExample(prev => (prev + 1) % examplePdfs.length);
  const prevExample = () =>
    setCurrentExample(prev => (prev - 1 + examplePdfs.length) % examplePdfs.length);

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
          Transform any PDF documents into concise, intelligent summaries using advanced AI technology.
        </p>
      </header>

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
                    !summaryRaw ? "opacity-50 cursor-not-allowed" : ""
                  }`}
                  title="Copy to clipboard"
                  disabled={!summaryRaw}
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
                    setUploadedFile(null);
                    setError("");
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
            {/* Summary: rendu business/sectionné */}
            <div className="space-y-6 mb-6 max-h-[320px] overflow-y-auto px-2">
              {!summaryRaw && !isProcessing && !error && (
                <div className="text-slate-400 italic">
                  No summary yet. Upload a PDF to get started.
                </div>
              )}
              {summaryRaw &&
                parseSections(summaryRaw).map((section, idx) => (
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
                      <ReactMarkdown>
                        {section.content}
                      </ReactMarkdown>
                    </div>
                  </div>
                ))}
            </div>
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
                  <p className="text-sm text-slate-400">Status</p>
                  <p className="font-semibold text-white">
                    {summaryRaw ? "✅" : "—"}
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
          <div className="flex items-center space-x-6 mb-4 md:mb-0">
            <div className="text-center md:text-left">
              <p className="text-lg font-semibold text-white">AWS Hackathon</p>
              <p className="text-slate-400">Built with ❤️ by Konan Othniel</p>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="p-3 bg-slate-700/50 hover:bg-slate-600/50 rounded-lg transition-colors"
            >
              <Github className="w-5 h-5 text-white" />
            </a>
            <a
              href="https://www.linkedin.com/in/othniel-konan-a54b4b242/"
              target="_blank"
              rel="noopener noreferrer"
              className="p-3 bg-slate-700/50 hover:bg-slate-600/50 rounded-lg transition-colors"
            >
              <Linkedin className="w-5 h-5 text-white" />
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default App;
