"use client";

import { useMemo, useRef, useState } from "react";
import {
  AudioLines,
  CheckCircle2,
  Download,
  Loader2,
  Sparkles,
  Upload,
  Wand2,
} from "lucide-react";

type Mode = "final_master" | "vocal" | "instrumental" | "mix";

const API_URL = "https://astromix-audio-api-689440192272.us-central1.run.app";

const modes: { id: Mode; label: string; desc: string; output: string }[] = [
  {
    id: "final_master",
    label: "Final Master",
    desc: "The finished WAV. Loud, clean, controlled, ready to send.",
    output: "astroman-final-master.wav",
  },
  {
    id: "vocal",
    label: "Vocal Polish",
    desc: "Clean, bright, forward lead vocal with space and pressure.",
    output: "astroman-vocal-polish.wav",
  },
  {
    id: "instrumental",
    label: "Instrumental Polish",
    desc: "Tighter low end, cleaner width, controlled master bus feel.",
    output: "astroman-instrumental-polish.wav",
  },
  {
    id: "mix",
    label: "Full Mix Polish",
    desc: "Balanced final pass for a complete mix before export.",
    output: "astroman-full-mix-polish.wav",
  },
];

const modeCopy: Record<Mode, { cta: string; ready: string; preview: string }> = {
  final_master: {
    cta: "Create Final WAV",
    ready: "Your final WAV is ready",
    preview: "Preview Final Master",
  },
  vocal: {
    cta: "Polish Vocal",
    ready: "Your vocal WAV is ready",
    preview: "Preview Vocal Polish",
  },
  instrumental: {
    cta: "Polish Instrumental",
    ready: "Your instrumental WAV is ready",
    preview: "Preview Instrumental Polish",
  },
  mix: {
    cta: "Polish Full Mix",
    ready: "Your mix WAV is ready",
    preview: "Preview Full Mix",
  },
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass-soft rounded-3xl px-5 py-4">
      <p className="text-xs uppercase tracking-[0.25em] text-white/45">{label}</p>
      <p className="mt-2 text-lg font-semibold text-white">{value}</p>
    </div>
  );
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Mode>("final_master");
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState("");
  const [processedUrl, setProcessedUrl] = useState("");
  const [debugInfo, setDebugInfo] = useState("");

  const inputRef = useRef<HTMLInputElement | null>(null);
  const activeMode = modes.find((item) => item.id === mode) || modes[0];

  const originalUrl = useMemo(() => {
    if (!file) return "";
    return URL.createObjectURL(file);
  }, [file]);

  async function processAudio() {
    if (!file) {
      setError("Upload an audio file first.");
      return;
    }

    setError("");
    setDebugInfo("");
    setProcessedUrl("");
    setIsProcessing(true);

    const target = `${API_URL}/process`;

    try {
      // Step 1: CORS preflight check
      setDebugInfo("Step 1: Testing CORS preflight...");
      try {
        const preflight = await fetch(target, { method: "OPTIONS" });
        const corsHeader = preflight.headers.get("access-control-allow-origin");
        setDebugInfo(`Step 1 OK: OPTIONS ${preflight.status}, CORS: ${corsHeader || "MISSING"}`);
      } catch (preErr) {
        setDebugInfo(`Step 1 FAIL: OPTIONS blocked — ${preErr instanceof Error ? preErr.message : "unknown"}`);
      }

      // Step 2: Send the actual file
      setDebugInfo((prev) => prev + "\nStep 2: Uploading file...");
      const body = new FormData();
      body.append("file", file);
      body.append("mode", mode);

      const response = await fetch(target, {
        method: "POST",
        body,
      });

      setDebugInfo((prev) => prev + `\nStep 2 OK: POST status=${response.status}, type=${response.headers.get("content-type")}, size=${response.headers.get("content-length") || "unknown"}`);

      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const data = await response.json();
          detail = data?.detail || detail;
        } catch {
          try {
            const text = await response.text();
            detail = text.slice(0, 200) || detail;
          } catch {
            // ignore
          }
        }
        throw new Error(`Backend error: ${detail}`);
      }

      // Step 3: Read the response blob
      setDebugInfo((prev) => prev + "\nStep 3: Reading audio response...");
      const blob = await response.blob();
      setDebugInfo((prev) => prev + `\nStep 3 OK: blob size=${blob.size}, type=${blob.type}`);

      if (blob.size < 1000) {
        const text = await blob.text();
        throw new Error(`Response too small (${blob.size} bytes): ${text.slice(0, 200)}`);
      }

      setProcessedUrl(URL.createObjectURL(blob));
      setDebugInfo((prev) => prev + "\nDONE: Audio ready!");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      const name = err instanceof Error ? err.name : "Unknown";

      let errorType = "UNKNOWN";
      if (msg.includes("Failed to fetch") || msg.includes("NetworkError") || msg.includes("ERR_FAILED")) {
        errorType = "NETWORK/CORS — Browser blocked the request. The backend may not be sending CORS headers on the response.";
      } else if (msg.includes("status 413")) {
        errorType = "PAYLOAD TOO LARGE — File is too big for the server.";
      } else if (msg.includes("status 500")) {
        errorType = "SERVER CRASH — Backend threw an error during processing.";
      } else if (msg.includes("status 502") || msg.includes("status 503")) {
        errorType = "SERVER DOWN — Cloud Run container is not running.";
      } else if (msg.includes("status 504") || msg.includes("TimeoutError")) {
        errorType = "TIMEOUT — Processing took too long.";
      } else if (msg.includes("Backend error")) {
        errorType = "BACKEND ERROR — Server returned an error message.";
      }

      setError(`${errorType}\n\nError: ${name}: ${msg}`);
      setDebugInfo((prev) => prev + `\nFAILED: ${errorType} — ${msg}`);
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <main className="noise min-h-screen bg-[#030303] px-4 py-6 text-white sm:px-6 lg:px-10">
      <section className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col justify-between rounded-[2rem] border border-white/10 bg-white/[0.025] p-4 shadow-2xl sm:rounded-[3rem] sm:p-8">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="glass flex h-11 w-11 items-center justify-center rounded-2xl">
              <AudioLines className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold tracking-[0.2em] text-white/55">ASTROMAN</p>
              <h1 className="text-xl font-bold">Mixing Engine</h1>
            </div>
          </div>
          <div className="hidden rounded-full border border-white/10 px-4 py-2 text-sm text-white/60 sm:block">
            v1.3.0 — Debug Mode
          </div>
        </header>

        <div className="grid gap-8 py-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-sm text-white/65">
              <Sparkles className="h-4 w-4" />
              Upload. Process. Final WAV.
            </div>
            <h2 className="mt-6 max-w-3xl text-5xl font-black tracking-[-0.06em] text-white sm:text-7xl lg:text-8xl">
              Turn raw audio into a finished master.
            </h2>
            <p className="mt-6 max-w-2xl text-base leading-7 text-white/62 sm:text-lg">
              A clean black and white audio app for vocals, instrumentals, and final masters. Built around the Astroman style chain.
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <Metric label="Default" value="Final Master" />
              <Metric label="Export" value="24-bit WAV" />
              <Metric label="Modes" value="4 Engines" />
            </div>
          </div>

          <div className="glass rounded-[2rem] p-4 sm:p-6">
            <div className="mb-5">
              <p className="text-sm uppercase tracking-[0.25em] text-white/45">Step 1</p>
              <h3 className="mt-2 text-2xl font-bold">Upload audio</h3>
            </div>

            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="group flex w-full cursor-pointer flex-col items-center justify-center rounded-[1.6rem] border border-dashed border-white/18 bg-black/28 px-5 py-9 text-center transition hover:border-white/35 hover:bg-white/[0.055]"
            >
              <Upload className="mb-4 h-8 w-8 text-white/65 transition group-hover:scale-105" />
              <span className="text-lg font-semibold">{file ? file.name : "Drop your audio here"}</span>
              <span className="mt-2 text-sm text-white/45">MP3, WAV, M4A, or AIFF</span>
            </button>

            <input
              ref={inputRef}
              type="file"
              accept="audio/*"
              className="hidden"
              onChange={(event) => {
                setFile(event.target.files?.[0] || null);
                setProcessedUrl("");
                setError("");
                setDebugInfo("");
              }}
            />

            <div className="mt-6">
              <p className="mb-3 text-sm uppercase tracking-[0.25em] text-white/45">Step 2</p>
              <div className="grid gap-3">
                {modes.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setMode(item.id);
                      setProcessedUrl("");
                    }}
                    className={`rounded-3xl border px-5 py-4 text-left transition ${
                      mode === item.id
                        ? "border-white bg-white text-black"
                        : "border-white/10 bg-white/[0.035] text-white hover:bg-white/[0.07]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-bold">{item.label}</p>
                        <p className={`mt-1 text-sm ${mode === item.id ? "text-black/60" : "text-white/45"}`}>
                          {item.desc}
                        </p>
                      </div>
                      {mode === item.id && <CheckCircle2 className="h-5 w-5 shrink-0" />}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {file && originalUrl && (
              <div className="mt-6 rounded-3xl border border-white/10 bg-black/25 p-4">
                <p className="mb-3 text-sm font-semibold text-white/60">Original Preview</p>
                <audio controls src={originalUrl} className="w-full" />
              </div>
            )}

            {error && (
              <div className="mt-5 rounded-2xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-white whitespace-pre-wrap font-mono">
                {error}
              </div>
            )}

            {debugInfo && (
              <div className="mt-3 rounded-2xl border border-yellow-500/30 bg-yellow-500/10 p-4 text-xs text-yellow-200 whitespace-pre-wrap font-mono">
                <p className="font-bold text-yellow-400 mb-2">DEBUG LOG</p>
                {debugInfo}
              </div>
            )}

            <button
              type="button"
              disabled={isProcessing}
              onClick={processAudio}
              className="mt-6 flex w-full items-center justify-center gap-3 rounded-full bg-white px-6 py-4 text-base font-black text-black transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isProcessing ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
              {isProcessing ? "Processing Final WAV" : modeCopy[mode].cta}
            </button>

            {processedUrl && (
              <div className="mt-6 rounded-[1.6rem] border border-white/12 bg-white/[0.045] p-4">
                <p className="text-sm font-semibold text-white/65">{modeCopy[mode].ready}</p>
                <p className="mt-1 text-xs text-white/40">{modeCopy[mode].preview}</p>
                <audio controls src={processedUrl} className="mt-4 w-full" />
                <a
                  href={processedUrl}
                  download={activeMode.output}
                  className="mt-4 flex w-full items-center justify-center gap-2 rounded-full border border-white/15 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10"
                >
                  <Download className="h-4 w-4" />
                  Download WAV
                </a>
              </div>
            )}
          </div>
        </div>

        <footer className="flex flex-col gap-2 border-t border-white/10 pt-5 text-sm text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <p>Preset based engine. Final WAV export implemented.</p>
          <p>Astroman Mixing Engine © 2026</p>
        </footer>
      </section>
    </main>
  );
}
