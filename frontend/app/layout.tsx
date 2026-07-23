import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "大衍 · 六爻问事",
  description: "基于传统六爻排盘算法的问事与解卦工作台",
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
