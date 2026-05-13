import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const maxDuration = 300;

const BACKEND_URL = "https://astromix-audio-api-689440192272.us-central1.run.app";

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();

    const response = await fetch(`${BACKEND_URL}/process`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await response.json().catch(() => null);
        return NextResponse.json(
          { detail: data?.detail || "Backend processing failed." },
          { status: response.status }
        );
      }

      const text = await response.text().catch(() => "");
      return NextResponse.json(
        { detail: text || "Backend processing failed." },
        { status: response.status }
      );
    }

    const audio = await response.arrayBuffer();
    const disposition = response.headers.get("content-disposition") || 'attachment; filename="astroman-output.wav"';

    return new NextResponse(audio, {
      status: 200,
      headers: {
        "Content-Type": "audio/wav",
        "Content-Disposition": disposition,
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "Proxy request failed.",
      },
      { status: 500 }
    );
  }
}
