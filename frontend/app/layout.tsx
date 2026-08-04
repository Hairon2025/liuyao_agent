import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "大衍 · 六爻问事",
  description: "基于传统六爻排盘算法的问事与解卦工作台",
};

// 明确使用设备宽度，确保 vinext 构建后的页面在手机上触发响应式断点。
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
