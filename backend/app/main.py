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

app = FastAPI(title="Astroman Audio Engine", version="1.5.0")

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
    return {"status": "ok", "engine": "astroman-audio", "version": "1.5.0"}


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


def delay_samples(audio: np.ndarray, sr: int, delay_ms: float, gain: float) -> np.ndarray:
    samples = int(sr * delay_ms / 1000.0)
    delayed = np.zeros_like(audio)
    if 0 < samples < len(audio):
        delayed[samples:] = audio[:-samples] * gain
    return delayed


def delay_stereo(audio: np.ndarray, sr: int, delay_ms_l: float, delay_ms_r: float, gain: float) -> np.ndarray:
    """Stereo delay with independent L/R times for width."""
    left = audio[:, 0:1]
    right = audio[:, 1:2]
    dl = delay_samples(np.column_stack([left, left]), sr, delay_ms_l, gain)[:, 0:1]
    dr = delay_samples(np.column_stack([right, right]), sr, delay_ms_r, gain)[:, 0:1]
    return np.column_stack([dl, dr]).astype(np.float32)


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


# ─── FX: BPM-SYNCED DELAYS + DUAL REVERB ─────────────────────────────────────


def vocal_fx(audio: np.ndarray, sr: int, bpm: float = 120.0) -> np.ndarray:
    """
    Two BPM-synced delays (1/4 and 1/2) + two reverbs (room + hall).
    All at -20dB aux level, matching the Pro Tools routing.
    Delays have high-pass EQ on returns.
    """
    quarter_ms = 60000.0 / bpm
    half_ms = quarter_ms * 2.0
    aux_gain = 0.1  # -20dB

    # 1/4 note delay — stereo with slight L/R offset for width
    d_quarter = delay_stereo(audio, sr, quarter_ms, quarter_ms + 15, aux_gain)
    d_quarter = highpass(d_quarter, sr, 200, order=2)

    # 1/2 note delay — stereo with L/R offset
    d_half = delay_stereo(audio, sr, half_ms, half_ms + 25, aux_gain * 0.85)
    d_half = highpass(d_half, sr, 200, order=2)

    # Reverb 1: Room (AIR Reverb style — early reflections, short)
    rev1 = np.zeros_like(audio)
    for ms_l, ms_r, g in [
        (12, 17, 0.04),
        (29, 38, 0.035),
        (43, 55, 0.03),
        (67, 79, 0.025),
        (89, 103, 0.02),
    ]:
        rev1 += delay_stereo(audio, sr, ms_l, ms_r, g)
    rev1 = highpass(rev1, sr, 300, order=2)
    rev1 = rev1 * aux_gain * 2.5

    # Reverb 2: Hall (ReVibe style — longer, wider, 24ms pre-delay)
    rev2 = np.zeros_like(audio)
    pre = 24
    for ms_l, ms_r, g in [
        (pre + 54, pre + 67, 0.028),
        (pre + 110, pre + 130, 0.024),
        (pre + 174, pre + 198, 0.019),
        (pre + 243, pre + 275, 0.015),
        (pre + 321, pre + 360, 0.011),
        (pre + 406, pre + 450, 0.008),
    ]:
        rev2 += delay_stereo(audio, sr, ms_l, ms_r, g)
    rev2 = highpass(rev2, sr, 250, order=2)
    rev2 = rev2 * aux_gain * 2.5

    return (audio + d_quarter + d_half + rev1 + rev2).astype(np.float32)


# ─── VOCAL POLISH ─────────────────────────────────────────────────────────────
# Chain: ChannelStrip EQ → CLA-76 compression → EQ3 HPF → de-ess → post-EQ → FX


def vocal_polish(audio: np.ndarray, sr: int, bpm: float = 120.0) -> np.ndarray:
    x = audio.copy()

    # Insert A: MH ChannelStrip EQ
    # +3.26dB air shelf at 10.6kHz
    x = high_shelf_like(x, sr, 10600, 0.45)
    # -0.96dB low shelf at 117Hz
    x = low_shelf_like(x, sr, 117, -0.10)

    # Insert B: CLA-76 (In Your Face, BLUEY, 4:1)
    # Fast attack, fast release, aggressive peak control
    x = compressor(x, sr,
        threshold_db=-24.0,
        ratio=3.5,
        attack_ms=2.0,
        release_ms=35.0,
        makeup_db=12.0,
    )
    # CLA-76 BLUEY harmonic saturation
    x = saturate(x, drive=1.4, mix=0.15)

    # Insert C: EQ3 high-pass at 132.6Hz, 18dB/oct
    x = highpass(x, sr, 132.6, order=3)

    # De-ess (sibilance gets louder after compression)
    x = de_ess(x, sr, 0.18)

    # Post shaping: presence lift
    x = high_shelf_like(x, sr, 7500, 0.14)
    x = band_adjust(x, sr, 200, 500, -0.04)

    # FX: BPM-synced delays + dual reverb at -20dB
    x = vocal_fx(x, sr, bpm)

    # Subtle stereo width
    x = stereo_width(x, 1.06)

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
    x = compressor(x, sr,
        threshold_db=-13.5,
        ratio=1.7,
        attack_ms=18,
        release_ms=140,
        makeup_db=0.4,
    )
    x = limiter(x, ceiling=0.92)
    return x


# ─── FULL MIX POLISH ─────────────────────────────────────────────────────────


def full_mix_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = highpass(audio, sr, 28, order=2)
    x = band_adjust(x, sr, 160, 420, -0.08)
    x = high_shelf_like(x, sr, 7000, 0.07)
    x = saturate(x, drive=1.15, mix=0.10)
    x = stereo_width(x, 1.05)
    x = compressor(x, sr,
        threshold_db=-14.5,
        ratio=1.8,
        attack_ms=20,
        release_ms=130,
        makeup_db=0.8,
    )
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
    x = compressor(x, sr,
        threshold_db=-15.0,
        ratio=1.9,
        attack_ms=22,
        release_ms=125,
        makeup_db=0.9,
    )

    current = rms_db(x)
    if current < -10.5:
        x = normalize_rms(x, -10.5)
    elif current > -8.0:
        x = normalize_rms(x, -8.8)

    x = limiter(x, ceiling=0.91)
    return x
