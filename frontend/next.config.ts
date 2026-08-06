import type { NextConfig } from "next";

const connectSources = ["'self'"];
const configuredApi = process.env.NEXT_PUBLIC_ROBOWEAVER_API;
if (configuredApi) {
  try {
    const apiUrl = new URL(configuredApi);
    if (apiUrl.protocol === "http:" || apiUrl.protocol === "https:") {
      connectSources.push(apiUrl.origin);
    }
  } catch {
    // Relative values are same-origin and already covered by 'self'.
  }
}

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}`,
  `connect-src ${connectSources.join(" ")}`,
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  ...(process.env.NODE_ENV === "production" ? ["upgrade-insecure-requests"] : []),
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  agentRules: false,
  // The app's own sidebar occupies the bottom-left corner; move the dev indicator
  // out of the way instead of letting it overlap real UI.
  devIndicators: {
    position: "bottom-right",
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
