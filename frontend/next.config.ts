import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The app's own sidebar occupies the bottom-left corner; move the dev indicator
  // out of the way instead of letting it overlap real UI.
  devIndicators: {
    position: "bottom-right",
  },
};

export default nextConfig;
