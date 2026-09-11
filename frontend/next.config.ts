import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Next 16 tự sinh frontend/AGENTS.md + frontend/CLAUDE.md mỗi lần dev/build.
  // Repo này chỉ có MỘT CLAUDE.md ở gốc (xem CLAUDE.md §12) — tắt để không đẻ file lạ.
  agentRules: false,
  // Ảnh Docker gọn: chỉ copy phần runtime thực sự cần.
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default config;
