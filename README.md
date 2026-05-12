# Astroman Mixing Engine

A mobile and web friendly audio processing app that exports a finished WAV.

Frontend:
- Next.js
- Tailwind CSS
- Inter font
- Black and white Tesla style interface
- Upload, process, preview, download
- Default product flow: Final Master to 24-bit WAV

Backend:
- FastAPI
- FFmpeg
- Python DSP chain
- Vocal Polish, Instrumental Polish, Full Mix Polish, Final Master

## Product flow

```txt
Upload audio
Select mode
Process
Preview result
Download final WAV
```

The primary mode is:

```txt
Final Master -> astroman-final-master.wav
```

## Local launch

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open:

```txt
http://localhost:3000
```

## Production launch

Recommended:

- Frontend on Vercel
- Backend on Google Cloud Run, Render, Railway, or Fly.io

Set this frontend environment variable in Vercel:

```txt
NEXT_PUBLIC_API_URL=https://your-backend-url.com
```

Then redeploy the frontend.

## Google Cloud Run backend deploy

From the repo root:

```bash
cd backend
gcloud run deploy astroman-audio-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900
```

After deploy, copy the Cloud Run URL into Vercel as `NEXT_PUBLIC_API_URL`.

## Render backend deploy

Render uses the included `backend/render.yaml` and Dockerfile.

Start command inside container:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Modes

### Final Master
The main export mode. It returns:

```txt
astroman-final-master.wav
```

Designed for a finished 24-bit WAV with:
- Low-end cleanup
- Low-mid control
- Presence lift
- Air lift
- Maserati-style glue approximation
- Light OTT-style multiband polish
- Stereo width control
- Final limiter safety

### Vocal Polish
Designed from the reference vocal chain:
- High pass cleanup
- Presence and air shaping
- FET style compression behavior
- Post compression high pass
- De-esser style softening
- Saturation
- Reverb and delay send
- Light mastering polish

### Instrumental Polish
Designed from pre-master to post-master instrumental behavior:
- Low-mid cleanup
- Low-end tightening
- Subtle brightness lift
- Stereo width control
- Controlled final limiting

### Full Mix Polish
Balanced polish for a complete mix.

## Important note

This app does not clone proprietary plugins. It recreates a similar practical chain with open DSP logic.
