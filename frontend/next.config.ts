import type { NextConfig } from "next";

// No /api rewrite here: src/app/api/[...path]/route.ts proxies to the backend
// instead, because a rewrite cannot attach the server-side API key header.
const nextConfig: NextConfig = {};

export default nextConfig;
