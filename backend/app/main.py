import shutil
import subprocess
import traceback
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from scipy.signal import butter, sosfilt, sosfiltfilt

BASE_DIR = Path(__file__).resolve().parent.parent
TMP_DIR = BASE_DIR / "tmp"
PROCESSED_DIR = BASE_DIR / "processed"
TMP_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Astroman Audio Engine", version="1.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)

VALID_MODES = {"vocal", "instrumental", "mix", "final_master"}
OUTPUT_NAMES = {
    "vocal": "astroman-vocal-polish",
    "instrumental": "astroman-instrumental-polish",
    "mix": "astroman-full-mix-polish",
    "final_master": "astroman-final-master",
}


@app.options("/process")
async def process_options(request: Request):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "86400",
        },
    )


@app.get("/")
def root():
    return {"status": "ok", "message": "Astroman Audio Engine is running."}


@app.get("/health")
def health():
    return {"status": "ok", "engine": "astroman-audio", "version": "1.6.0"}


@app.post("/process")
async def process_endpoint(
    file: UploadFile = File(...),
    mode: str = Form("final_master"),
    bpm: float = Form(120.0),
):
    if mode not in VALID_MODES:
        return JSONResponse(status_code=400, content={"detail": "Invalid mode."})

    if bpm < 40 or bpm > 300:
        bpm = 120.0

    job_id = uuid.uuid4().hex
    source_path = TMP_DIR / f"{job_id}_{safe_name(file.filename or 'upload')}"
    wav_path = TMP_DIR / f"{job_id}_input.wav"
    output_wav = PROCESSED_DIR / f"{job_id}_{OUTPUT_NAMES[mode]}.wav"
    output_mp3 = PROCESSED_DIR / f"{job_id}_{OUTPUT_NAMES[mode]}.mp3"

    try:
        with source_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(
            f"PROCESS START job={job_id} mode={mode} bpm={bpm} file={file.filename} size={source_path.stat().st_size}",
            flush=True,
        )

        convert_to_wav(source_path, wav_path)

        audio, sr = sf.read(wav_path, always_2d=True)
        audio = sanitize_audio(audio)

        if mode == "vocal":
            processed = vocal_polish(audio, sr, bpm)
        elif mode == "instrumental":
            processed = instrumental_polish(audio, sr)
        elif mode == "mix":
            processed = full_mix_polish(audio, sr)
        else:
            processed = final_master(audio, sr)

        processed = final_safety(processed, target_peak=0.95)

        sf.write(output_wav, processed, sr, subtype="PCM_24")

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(output_wav),
                "-codec:a", "libmp3lame",
                "-b:a", "320k",
                str(output_mp3),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        mp3_size = output_mp3.stat().st_size

        print(
            f"PROCESS OK job={job_id} wav_size={output_wav.stat().st_size} mp3_size={mp3_size}",
            flush=True,
        )

        return FileResponse(
            output_mp3,
            media_type="audio/mpeg",
            filename=f"{OUTPUT_NAMES[mode]}.mp3",
        )

    except subprocess.CalledProcessError as exc:
        print("FFMPEG ERROR", flush=True)
        print(exc, flush=True)
        print(traceback.format_exc(), flush=True)
        return JSONResponse(status_code=500, content={"detail": "FFmpeg could not process this audio file."})

    except Exception as exc:
        print("PROCESSING ERROR", flush=True)
        print(str(exc), flush=True)
        print(traceback.format_exc(), flush=True)
        return JSONResponse(status_code=500, content={"detail": f"Processing error: {str(exc)}"})

    finally:
        for path in (source_path, wav_path, output_wav):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass


# ─── UTILITIES ────────────────────────────────────────────────────────────────


def safe_name(name: str) -> str:
    clean = "".join(
        char for char in name if char.isalnum() or char in {".", "_", "-", " "}
    ).strip()
    return clean[:120] or "upload"


def convert_to_wav(input_path: Path, output_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-acodec", "pcm_f32le", "-ar", "48000", str(output_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def sanitize_audio(audio: np.ndarray) -> np.ndarray:
    audio = np.nan_to_num(audio.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    if audio.shape[1] > 2:
        audio = audio[:, :2]
    return np.clip(audio, -1.0, 1.0)


# ─── DSP BUILDING BLOCKS ─────────────────────────────────────────────────────


def highpass(audio: np.ndarray, sr: int, freq: float, order: int = 3) -> np.ndarray:
    sos = butter(order, freq, btype="highpass", fs=sr, output="sos")
    return sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def lowpass(audio: np.ndarray, sr: int, freq: float, order: int = 2) -> np.ndarray:
    sos = butter(order, freq, btype="lowpass", fs=sr, output="sos")
    return sosfiltfilt(sos, audio, axis=0).astype(np.float32)


def high_shelf_like(audio: np.ndarray, sr: int, cutoff: float, amount: float) -> np.ndarray:
    sos = butter(2, cutoff, btype="highpass", fs=sr, output="sos")
    high = sosfiltfilt(sos, audio, axis=0)
    return (audio + high * amount).astype(np.float32)


def low_shelf_like(audio: np.ndarray, sr: int, cutoff: float, amount: float) -> np.ndarray:
    sos = butter(2, cutoff, btype="lowpass", fs=sr, output="sos")
    low = sosfiltfilt(sos, audio, axis=0)
    return (audio + low * amount).astype(np.float32)


def band_adjust(audio: np.ndarray, sr: int, low_freq: float, high_freq: float, amount: float) -> np.ndarray:
    sos = butter(2, [low_freq, high_freq], btype="bandpass", fs=sr, output="sos")
    band = sosfiltfilt(sos, audio, axis=0)
    return (audio + band * amount).astype(np.float32)


def band_cut(audio: np.ndarray, sr: int, low_freq: float, high_freq: float, amount: float) -> np.ndarray:
    sos = butter(2, [low_freq, high_freq], btype="bandpass", fs=sr, output="sos")
    band = sosfiltfilt(sos, audio, axis=0)
    return (audio - band * amount).astype(np.float32)


def db_to_amp(db):
    return np.power(10.0, np.asarray(db) / 20.0)


def rms_db(audio: np.ndarray) -> float:
    return float(20.0 * np.log10(np.sqrt(np.mean(audio**2)) + 1e-9))


def normalize_rms(audio: np.ndarray, target_db: float) -> np.ndarray:
    gain = db_to_amp(target_db - rms_db(audio))
    return (audio * gain).astype(np.float32)


def compressor(
    audio: np.ndarray,
    sr: int,
    threshold_db: float,
    ratio: float,
    attack_ms: float,
    release_ms: float,
    makeup_db: float,
) -> np.ndarray:
    mono = np.mean(audio, axis=1)
    env = np.abs(mono) + 1e-9

    attack = np.exp(-1.0 / max(sr * attack_ms / 1000.0, 1.0))
    release = np.exp(-1.0 / max(sr * release_ms / 1000.0, 1.0))

    smoothed = np.empty_like(env)
    previous = env[0]

    for i, value in enumerate(env):
        coeff = attack if value > previous else release
        previous = coeff * previous + (1.0 - coeff) * value
        smoothed[i] = previous

    level_db = 20.0 * np.log10(smoothed + 1e-9)
    over_db = np.maximum(level_db - threshold_db, 0.0)
    gain_db = -over_db * (1.0 - 1.0 / ratio) + makeup_db

    return (audio * db_to_amp(gain_db)[:, None]).astype(np.float32)


def de_ess(audio: np.ndarray, sr: int, amount: float = 0.22) -> np.ndarray:
    sos = butter(2, [5200, 10500], btype="bandpass", fs=sr, output="sos")
    ess = sosfilt(sos, audio, axis=0)
    ess_level = np.abs(np.mean(ess, axis=1))
    trigger = np.clip((ess_level - 0.018) / 0.09, 0.0, 1.0)
    reduction = 1.0 - trigger[:, None] * amount
    return (audio - ess * (1.0 - reduction)).astype(np.float32)


def saturate(audio: np.ndarray, drive: float = 1.25, mix: float = 0.18) -> np.ndarray:
    wet = np.tanh(audio * drive) / np.tanh(drive)
    return (audio * (1.0 - mix) + wet * mix).astype(np.float32)


def delay_mono(audio: np.ndarray, sr: int, delay_ms: float, gain: float, feedback: float = 0.0) -> np.ndarray:
    """Mono delay with feedback. Returns signal as stereo (duplicated L/R)."""
    mono = np.mean(audio, axis=1)
    samples = int(sr * delay_ms / 1000.0)
    out = np.zeros_like(mono)
    if samples > 0 and samples < len(mono):
        out[samples:] = mono[:-samples] * gain
        if feedback > 0:
            fb_gain = gain
            offset = samples
            for _ in range(8):
                fb_gain *= feedback
                offset += samples
                if offset >= len(mono) or fb_gain < 0.001:
                    break
                out[offset:] += mono[:-offset] * fb_gain
    return np.column_stack([out, out]).astype(np.float32)


def reverb_wide(audio: np.ndarray, sr: int, taps, pre_delay_ms: float = 0, hpf: float = 200, lpf: float = 8000, gain: float = 1.0) -> np.ndarray:
    """Wide stereo reverb with independent L/R tap times."""
    mono = np.mean(audio, axis=1)
    n = len(mono)
    out_l = np.zeros(n, dtype=np.float32)
    out_r = np.zeros(n, dtype=np.float32)
    pre = int(sr * pre_delay_ms / 1000.0)
    
    for ms_l, ms_r, g in taps:
        sl = pre + int(sr * ms_l / 1000.0)
        sr_idx = pre + int(sr * ms_r / 1000.0)
        if 0 < sl < n:
            out_l[sl:] += mono[:-sl] * g
        if 0 < sr_idx < n:
            out_r[sr_idx:] += mono[:-sr_idx] * g
    
    result = np.column_stack([out_l, out_r]).astype(np.float32)
    result = highpass(result, sr, hpf, order=2)
    result = lowpass(result, sr, lpf, order=2)
    return (result * gain).astype(np.float32)


def stereo_width(audio: np.ndarray, width: float) -> np.ndarray:
    left = audio[:, 0]
    right = audio[:, 1]
    mid = (left + right) * 0.5
    side = (left - right) * 0.5 * width
    return np.stack([mid + side, mid - side], axis=1).astype(np.float32)


def limiter(audio: np.ndarray, ceiling: float = 0.92) -> np.ndarray:
    return np.tanh(audio / ceiling) * ceiling


def final_safety(audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio)) + 1e-9)
    if peak > target_peak:
        audio = audio * (target_peak / peak)
    return np.clip(audio, -0.99, 0.99).astype(np.float32)


# ─── VOCAL POLISH ─────────────────────────────────────────────────────────────
# Dry chain: ChannelStrip EQ → CLA-76 compression → EQ3 HPF → de-ess → post-EQ
# FX: 1/8 delay (mono, filtered, with feedback) + 1/4, 1/2 delays + wide reverbs


def vocal_polish(audio: np.ndarray, sr: int, bpm: float = 120.0) -> np.ndarray:
    x = audio.copy()

    # ChannelStrip: air boost + low cut
    x = high_shelf_like(x, sr, 10600, 0.45)
    x = low_shelf_like(x, sr, 117, -0.10)

    # CLA-76: aggressive compression with saturation
    x = compressor(x, sr, threshold_db=-24.0, ratio=3.5, attack_ms=2.0, release_ms=35.0, makeup_db=12.0)
    x = saturate(x, drive=1.4, mix=0.15)

    # EQ3 HPF + de-ess
    x = highpass(x, sr, 132.6, order=3)
    x = de_ess(x, sr, 0.18)

    # Post-EQ: presence + low-mid shape
    x = high_shelf_like(x, sr, 7500, 0.14)
    x = band_adjust(x, sr, 200, 500, -0.04)

    # ─── FX: BPM-synced delays + wide reverbs ───
    eighth_ms = 60000.0 / bpm / 2       # 250ms at 120 BPM
    quarter_ms = 60000.0 / bpm           # 500ms
    half_ms = quarter_ms * 2              # 1000ms

    # 1/8 delay: PRIMARY delay with feedback (creates 1/4 and 1/2 echoes naturally)
    # Mono, with HPF 177Hz + notch at 2.47kHz + LPF 4kHz
    d_eighth = delay_mono(x, sr, eighth_ms, gain=0.16, feedback=0.4)
    d_eighth = highpass(d_eighth, sr, 177, order=3)
    d_eighth = band_cut(d_eighth, sr, 2000, 3000, 0.6)
    d_eighth = lowpass(d_eighth, sr, 4000, order=2)

    # 1/4 delay: secondary, quiet
    d_quarter = delay_mono(x, sr, quarter_ms, gain=0.035)
    d_quarter = highpass(d_quarter, sr, 177, order=3)
    d_quarter = band_cut(d_quarter, sr, 2000, 3000, 0.6)
    d_quarter = lowpass(d_quarter, sr, 4000, order=2)

    # 1/2 delay: very subtle
    d_half = delay_mono(x, sr, half_ms, gain=0.015)
    d_half = highpass(d_half, sr, 177, order=3)
    d_half = band_cut(d_half, sr, 2000, 3000, 0.6)
    d_half = lowpass(d_half, sr, 4000, order=2)

    # Room reverb: short, bright, wide stereo spread
    r1 = reverb_wide(x, sr, [
        (5, 22, 0.05), (12, 38, 0.045), (24, 55, 0.040),
        (40, 78, 0.034), (60, 108, 0.028), (88, 145, 0.022),
        (122, 190, 0.016), (168, 248, 0.011), (225, 318, 0.007)
    ], pre_delay_ms=0, hpf=180, lpf=8000, gain=0.40)

    # Hall reverb: longer, wider, with pre-delay
    r2 = reverb_wide(x, sr, [
        (35, 90, 0.038), (80, 165, 0.032), (140, 260, 0.026),
        (215, 370, 0.020), (305, 490, 0.015), (410, 630, 0.010),
        (540, 790, 0.007), (700, 980, 0.004)
    ], pre_delay_ms=24, hpf=180, lpf=6500, gain=0.40)

    # Combine FX
    fx = d_eighth + d_quarter + d_half + r1 + r2
    x = x + fx

    # Subtle stereo width
    x = stereo_width(x, 1.02)

    return x


# ─── INSTRUMENTAL POLISH ─────────────────────────────────────────────────────


def instrumental_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = audio.copy()
    x = highpass(x, sr, 30, order=2)
    x = band_adjust(x, sr, 120, 500, -0.12)
    x = band_adjust(x, sr, 60, 120, -0.04)
    x = high_shelf_like(x, sr, 6500, 0.055)
    x = saturate(x, drive=1.12, mix=0.08)
    x = stereo_width(x, 1.08)
    x = compressor(x, sr, threshold_db=-13.5, ratio=1.7, attack_ms=18, release_ms=140, makeup_db=0.4)
    x = limiter(x, ceiling=0.92)
    return x


# ─── FULL MIX POLISH ─────────────────────────────────────────────────────────


def full_mix_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = highpass(audio, sr, 28, order=2)
    x = band_adjust(x, sr, 160, 420, -0.08)
    x = high_shelf_like(x, sr, 7000, 0.07)
    x = saturate(x, drive=1.15, mix=0.10)
    x = stereo_width(x, 1.05)
    x = compressor(x, sr, threshold_db=-14.5, ratio=1.8, attack_ms=20, release_ms=130, makeup_db=0.8)
    x = limiter(x, ceiling=0.92)
    return x


# ─── FINAL MASTER ────────────────────────────────────────────────────────────


def final_master(audio: np.ndarray, sr: int) -> np.ndarray:
    x = highpass(audio, sr, 26, order=2)
    x = low_shelf_like(x, sr, 95, -0.025)
    x = band_adjust(x, sr, 120, 500, -0.10)
    x = band_adjust(x, sr, 1800, 4800, 0.035)
    x = high_shelf_like(x, sr, 7200, 0.075)
    x = saturate(x, drive=1.18, mix=0.11)
    x = stereo_width(x, 1.07)
    x = compressor(x, sr, threshold_db=-15.0, ratio=1.9, attack_ms=22, release_ms=125, makeup_db=0.9)

    current = rms_db(x)
    if current < -10.5:
        x = normalize_rms(x, -10.5)
    elif current > -8.0:
        x = normalize_rms(x, -8.8)

    x = limiter(x, ceiling=0.91)
    return x
