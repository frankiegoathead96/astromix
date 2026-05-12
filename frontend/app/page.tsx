"use client";

import { useMemo, useRef, useState } from "react";
import { AudioLines, CheckCircle2, Download, Loader2, Sparkles, Upload, Wand2 } from "lucide-react";

type Mode = "final_master" | "vocal" | "instrumental" | "mix";

const modes: { id: Mode; label: string; desc: string; output: string }[] = [
  {
    id: "final_master",
    label: "Final Master",
    desc: "The finished WAV. Loud, clean, controlled, ready to send.",
    output: "astroman-final-master.wav"
  },
  {
    id: "vocal",
    label: "Vocal Polish",
    desc: "Clean, bright, forward lead vocal with space and pressure.",
    output: "astroman-vocal-polish.wav"
  },
  {
    id: "instrumental",
    label: "Instrumental Polish",
    desc: "Tighter low end, cleaner width, controlled master bus feel.",
    output: "astroman-instrumental-polish.wav"
  },
  {
    id: "mix",
    label: "Full Mix Polish",
    desc: "Balanced final pass for a complete mix before export.",
    output: "astroman-full-mix-polish.wav"
  }
];

const modeCopy: Record<Mode, { cta: string; ready: string; preview: string }> = {
  final_master: {
    cta: "Create Final WAV",
    ready: "Your final WAV is ready",
    preview: "Preview Final Master"
  },
  vocal: {
    cta: "Polish Vocal",
    ready: "Your vocal WAV is ready",
    preview: "Preview Vocal Polish"
  },
  instrumental: {
    cta: "Polish Instrumental",
    ready: "Your instrumental WAV is ready",
    preview: "Preview Instrumental Polish"
  },
  mix: {
    cta: "Polish Full Mix",
    ready: "Your mix WAV is ready",
    preview: "Preview Full Mix"
  }
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<Mode>("final_master");
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState("");
  const [processedUrl, setProcessedUrl] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const apiUrl = useMemo(() => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000", []);
  const activeMode = modes.find((item) => item.id === mode) || modes[0];
  const originalUrl = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);

  async function processAudio() {
    if (!file) {
      setError("Upload an audio file first.");
      return;
    }

    setError("");
    setProcessedUrl("");
    setIsProcessing(true);

    try {
      const body = new FormData();
      body.append("file", file);
      body.append("mode", mode);

      const response = await fetch(`${apiUrl}/process`, {
        method: "POST",
        body
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Processing failed.");
      }

      const blob = await response.blob();
      setProcessedUrl(URL.createObjectURL(blob));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <main className="noise relative min-h-screen overflow-x-hidden bg-[#030303] px-4 py-4 text-white sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute left-1/2 top-[-22rem] h-[48rem] w-[48rem] -translate-x-1/2 rounded-full bg-white/10 blur-[150px]" />
      <div className="pointer-events-none absolute bottom-[-20rem] right-[-10rem] h-[36rem] w-[36rem] rounded-full bg-white/8 blur-[120px]" />

      <section className="relative mx-auto flex min-h-[calc(100svh-2rem)] w-full max-w-6xl flex-col justify-between rounded-[2rem] border border-white/10 bg-black/30 p-4 shadow-glass sm:p-6 lg:p-8">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="glass flex h-11 w-11 items-center justify-center rounded-2xl">
              <AudioLines className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.34em] text-white/45">Astroman</p>
              <h1 className="text-lg font-semibold tracking-tight">Mixing Engine</h1>
            </div>
          </div>
          <div className="hidden rounded-full border border-white/10 px-4 py-2 text-xs font-medium text-white/60 sm:block">
            Web + Mobile Ready
          </div>
        </header>

        <div className="grid flex-1 items-center gap-8 py-9 lg:grid-cols-[0.92fr_1.08fr] lg:py-14">
          <div className="space-y-7">
            <div className="space-y-4">
              <p className="inline-flex rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs font-semibold uppercase tracking-[0.25em] text-white/55">
                Upload. Process. Final WAV.
              </p>
              <h2 className="max-w-xl text-5xl font-black tracking-[-0.06em] text-white sm:text-6xl lg:text-7xl">
                Turn raw audio into a finished master.
              </h2>
              <p className="max-w-lg text-base leading-7 text-white/58 sm:text-lg">
                A clean black and white audio app for vocals, instrumentals, and final masters. Built around the Astroman style chain.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-2 rounded-[1.6rem] border border-white/10 bg-white/[0.035] p-2">
              <Metric label="EQ" value="Clean" />
              <Metric label="Bus" value="Glue" />
              <Metric label="Export" value="WAV" />
            </div>

            <div className="glass-soft rounded-[1.5rem] p-4 text-sm leading-6 text-white/56">
              <div className="mb-2 flex items-center gap-2 text-white">
                <Sparkles className="h-4 w-4" />
                <span className="font-bold">Default mode is Final Master.</span>
              </div>
              Upload a full mix, beat, or vocal. The app returns a 24-bit WAV with final polish and a clean download flow.
            </div>
          </div>

          <div className="glass rounded-[2rem] p-4 sm:p-5">
            <div
              onClick={() => inputRef.current?.click()}
              className="group flex cursor-pointer flex-col items-center justify-center rounded-[1.6rem] border border-dashed border-white/18 bg-black/28 px-5 py-9 text-center transition hover:border-white/35 hover:bg-white/[0.055]"
            >
              <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-3xl bg-white text-black transition group-hover:scale-105">
                <Upload className="h-7 w-7" />
              </div>
              <p className="max-w-full truncate text-xl font-bold tracking-tight">{file ? file.name : "Drop your audio here"}</p>
              <p className="mt-2 text-sm text-white/48">MP3, WAV, M4A, or AIFF</p>
              <input
                ref={inputRef}
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={(event) => {
                  setFile(event.target.files?.[0] || null);
                  setProcessedUrl("");
                  setError("");
                }}
              />
            </div>

            <div className="mt-5 grid gap-3">
              {modes.map((item) => (
                <button
                  key={item.id}
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
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="font-bold tracking-tight">{item.label}</p>
                      <p className={`mt-1 text-sm ${mode === item.id ? "text-black/55" : "text-white/45"}`}>{item.desc}</p>
                    </div>
                    {mode === item.id && <CheckCircle2 className="h-5 w-5 shrink-0" />}
                  </div>
                </button>
              ))}
            </div>

            {file && originalUrl && (
              <div className="mt-5 rounded-3xl border border-white/10 bg-black/30 p-4">
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.25em] text-white/35">Original Preview</p>
                <audio className="w-full" controls src={originalUrl} />
              </div>
            )}

            {error && <p className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70">{error}</p>}

            <button
              onClick={processAudio}
              disabled={isProcessing}
              className="mt-5 flex w-full items-center justify-center gap-3 rounded-full bg-white px-6 py-4 text-sm font-extrabold uppercase tracking-[0.18em] text-black transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isProcessing ? <Loader2 className="h-5 w-5 animate-spin" /> : <Wand2 className="h-5 w-5" />}
              {isProcessing ? "Processing Final WAV" : modeCopy[mode].cta}
            </button>

            {processedUrl && (
              <div className="mt-5 rounded-[1.6rem] border border-white/10 bg-white/[0.045] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.25em] text-white/35">{modeCopy[mode].ready}</p>
                <p className="mb-3 mt-1 text-sm text-white/55">{modeCopy[mode].preview}</p>
                <audio className="w-full" controls src={processedUrl} />
                <a
                  href={processedUrl}
                  download={activeMode.output}
                  className="mt-4 flex w-full items-center justify-center gap-3 rounded-full border border-white/15 px-5 py-3 text-sm font-bold text-white transition hover:bg-white hover:text-black"
                >
                  <Download className="h-4 w-4" />
                  Download WAV
                </a>
              </div>
            )}
          </div>
        </div>

        <footer className="flex flex-col justify-between gap-3 border-t border-white/10 pt-5 text-xs text-white/35 sm:flex-row">
          <p>Preset based engine. Final WAV export implemented.</p>
          <p>Astroman Mixing Engine © 2026</p>
        </footer>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] bg-white/[0.045] p-4 text-center">
      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-white/34">{label}</p>
      <p className="mt-2 text-lg font-black tracking-tight">{value}</p>
    </div>
  );
}
