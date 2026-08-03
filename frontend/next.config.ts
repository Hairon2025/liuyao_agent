import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 为 Docker / 普通 Node.js 服务器生成可独立运行的生产产物。
  output: "standalone",
};

export default nextConfig;
