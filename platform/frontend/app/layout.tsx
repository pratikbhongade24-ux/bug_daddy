import type { Metadata } from "next";
import { Manrope, Sora } from "next/font/google";
import { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";

import "./globals.css";

const displayFont = Sora({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
});

const bodyFont = Manrope({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Bug Daddy Platform",
  description: "Control room UI for trigger ingestion, multi-agent orchestration, and autonomous code maintenance.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html className={`${displayFont.variable} ${bodyFont.variable}`} lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
