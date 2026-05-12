import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Astroman Mixing Engine",
  description: "Upload audio and export a polished final WAV."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
