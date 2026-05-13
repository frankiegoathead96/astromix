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

app = FastAPI(title="Astroman Audio Engine", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

VALID_MODES = {"vocal", "instrumental", "mix", "final_master"}
OUTPUT_NAMES = {
    "vocal": "astroman-vocal-polish.wav",
    "instrumental": "astroman-instrumental-polish.wav",
    "mix": "astroman-full-mix-polish.wav",
    "final_master": "astroman-final-master.wav",
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
    return {"status": "ok", "engine": "astroman-audio", "version": "1.2.0"}


@app.post("/process")
async def process_endpoint(file: UploadFile = File(...), mode: str = Form("final_master")):
    if mode not in VALID_MODES:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid mode."},
        )

    job_id = uuid.uuid4().hex
    source_path = TMP_DIR / f"{job_id}_{safe_name(file.filename or 'upload')}"
    wav_path = TMP_DIR / f"{job_id}_input.wav"
    output_path = PROCESSED_DIR / f"{job_id}_{OUTPUT_NAMES[mode]}"

    try:
        with source_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(
            f"PROCESS START job={job_id} mode={mode} file={file.filename} size={source_path.stat().st_size}",
            flush=True,
        )

        convert_to_wav(source_path, wav_path)

        audio, sr = sf.read(wav_path, always_2d=True)
        audio = sanitize_audio(audio)

        if mode == "vocal":
            processed = vocal_polish(audio, sr)
        elif mode == "instrumental":
            processed = instrumental_polish(audio, sr)
        elif mode == "mix":
            processed = full_mix_polish(audio, sr)
        else:
            processed = final_master(audio, sr)

        processed = final_safety(processed, target_peak=0.92)

        sf.write(output_path, processed, sr, subtype="PCM_24")

        print(
            f"PROCESS OK job={job_id} output={output_path.name} size={output_path.stat().st_size}",
            flush=True,
        )

        return FileResponse(
            output_path,
            media_type="audio/wav",
            filename=OUTPUT_NAMES[mode],
        )

    except subprocess.CalledProcessError as exc:
        print("FFMPEG ERROR", flush=True)
        print(exc, flush=True)
        print(traceback.format_exc(), flush=True)

        return JSONResponse(
            status_code=500,
            content={"detail": "FFmpeg could not read this audio file."},
        )

    except Exception as exc:
        print("PROCESSING ERROR", flush=True)
        print(str(exc), flush=True)
        print(traceback.format_exc(), flush=True)

        return JSONResponse(
            status_code=500,
            content={"detail": f"Processing error: {str(exc)}"},
        )

    finally:
        for path in (source_path, wav_path):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass


def safe_name(name: str) -> str:
    clean = "".join(
        char for char in name if char.isalnum() or char in {".", "_", "-", " "}
    ).strip()
    return clean[:120] or "upload"


def convert_to_wav(input_path: Path, output_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-acodec",
        "pcm_f32le",
        "-ar",
        "48000",
        str(output_path),
    ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def sanitize_audio(audio: np.ndarray) -> np.ndarray:
    audio = np.nan_to_num(
        audio.astype(np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)

    if audio.shape[1] > 2:
        audio = audio[:, :2]

    return np.clip(audio, -1.0, 1.0)


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


def band_adjust(
    audio: np.ndarray,
    sr: int,
    low_freq: float,
    high_freq: float,
    amount: float,
) -> np.ndarray:
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


def compressor_safe(
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


def vocal_fx(audio: np.ndarray, sr: int) -> np.ndarray:
    slap_l = delay_samples(audio, sr, 58, 0.16)
    slap_r = delay_samples(audio[:, ::-1], sr, 116, 0.12)

    main_l = delay_samples(audio, sr, 285, 0.10)
    main_r = delay_samples(audio[:, ::-1], sr, 355, 0.09)

    reverb = np.zeros_like(audio)

    for delay_ms, gain in [
        (42, 0.10),
        (87, 0.08),
        (131, 0.065),
        (181, 0.052),
        (239, 0.038),
    ]:
        reverb += delay_samples(audio[:, ::-1], sr, delay_ms, gain)

    fx = slap_l + slap_r + main_l + main_r + reverb
    fx = highpass(fx, sr, 250, order=2)
    fx = high_shelf_like(fx, sr, 7200, 0.18)

    return (audio + fx).astype(np.float32)


def stereo_width(audio: np.ndarray, width: float) -> np.ndarray:
    left = audio[:, 0]
    right = audio[:, 1]

    mid = (left + right) * 0.5
    side = (left - right) * 0.5 * width

    widened = np.stack([mid + side, mid - side], axis=1)

    return widened.astype(np.float32)


def ott_style(audio: np.ndarray, sr: int, depth: float) -> np.ndarray:
    low_sos = butter(2, 180, btype="lowpass", fs=sr, output="sos")
    high_sos = butter(2, 5200, btype="highpass", fs=sr, output="sos")

    low = sosfiltfilt(low_sos, audio, axis=0)
    high = sosfiltfilt(high_sos, audio, axis=0)
    mid = audio - low - high

    low_c = compressor_safe(low, sr, -20, 2.2, 18, 120, 0.5)
    mid_c = compressor_safe(mid, sr, -24, 2.6, 10, 95, 1.2)
    high_c = compressor_safe(high, sr, -28, 2.0, 3, 80, 2.4)

    wet = low_c + mid_c + high_c

    return (audio * (1.0 - depth) + wet * depth).astype(np.float32)


def limiter(audio: np.ndarray, ceiling: float = 0.92) -> np.ndarray:
    return np.tanh(audio / ceiling) * ceiling


def final_safety(audio: np.ndarray, target_peak: float = 0.92) -> np.ndarray:
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio)) + 1e-9)

    if peak > target_peak:
        audio = audio * (target_peak / peak)

    return np.clip(audio, -0.99, 0.99).astype(np.float32)


def vocal_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = normalize_rms(audio, -22.0)
    x = highpass(x, sr, 115, order=4)
    x = high_shelf_like(x, sr, 9000, 0.18)
    x = compressor_safe(
        x,
        sr,
        threshold_db=-25.0,
        ratio=4.0,
        attack_ms=4.5,
        release_ms=45.0,
        makeup_db=7.0,
    )
    x = highpass(x, sr, 132.6, order=3)
    x = de_ess(x, sr, 0.2)
    x = saturate(x, drive=1.35, mix=0.16)
    x = vocal_fx(x, sr)
    x = high_shelf_like(x, sr, 6200, 0.08)
    x = band_adjust(x, sr, 180, 500, -0.06)
    x = ott_style(x, sr, depth=0.22)
    x = stereo_width(x, width=1.08)
    x = normalize_rms(x, -13.5)
    x = limiter(x, ceiling=0.9)

    return x


def instrumental_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = audio.copy()
    x = highpass(x, sr, 30, order=2)
    x = band_adjust(x, sr, 120, 500, -0.12)
    x = band_adjust(x, sr, 60, 120, -0.04)
    x = high_shelf_like(x, sr, 6500, 0.055)
    x = saturate(x, drive=1.12, mix=0.08)
    x = ott_style(x, sr, depth=0.18)
    x = stereo_width(x, width=1.08)
    x = compressor_safe(
        x,
        sr,
        threshold_db=-13.5,
        ratio=1.7,
        attack_ms=18,
        release_ms=140,
        makeup_db=0.4,
    )
    x = limiter(x, ceiling=0.92)

    return x


def full_mix_polish(audio: np.ndarray, sr: int) -> np.ndarray:
    x = highpass(audio, sr, 28, order=2)
    x = band_adjust(x, sr, 160, 420, -0.08)
    x = high_shelf_like(x, sr, 7000, 0.07)
    x = saturate(x, drive=1.15, mix=0.10)
    x = ott_style(x, sr, depth=0.16)
    x = stereo_width(x, width=1.05)
    x = compressor_safe(
        x,
        sr,
        threshold_db=-14.5,
        ratio=1.8,
        attack_ms=20,
        release_ms=130,
        makeup_db=0.8,
    )
    x = limiter(x, ceiling=0.92)

    return x


def final_master(audio: np.ndarray, sr: int) -> np.ndarray:
    x = highpass(audio, sr, 26, order=2)
    x = low_shelf_like(x, sr, 95, -0.025)
    x = band_adjust(x, sr, 120, 500, -0.10)
    x = band_adjust(x, sr, 1800, 4800, 0.035)
    x = high_shelf_like(x, sr, 7200, 0.075)
    x = saturate(x, drive=1.18, mix=0.11)
    x = ott_style(x, sr, depth=0.20)
    x = stereo_width(x, width=1.07)
    x = compressor_safe(
        x,
        sr,
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
