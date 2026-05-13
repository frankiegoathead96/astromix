/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: "https://astromix-audio-api-689440192272.us-central1.run.app/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
