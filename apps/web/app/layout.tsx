import type { Metadata } from "next";
import Link from "next/link";
import { Activity, ScanLine } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoQA Agent",
  description: "Automated QA dashboard for page discovery, form submission coverage, and bug handoff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen pb-10">
          <header className="mb-8 border-b border-slate/10 bg-white">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3.5 sm:px-8">
              <Link href="/" className="inline-flex items-center gap-2.5 font-display text-xl font-semibold tracking-tight text-ink">
                <span className="rounded-lg bg-ink p-2 text-white"><ScanLine className="h-5 w-5" aria-hidden="true" /></span>
                AutoQA
              </Link>
              <a className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate hover:bg-sand" href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/health`} target="_blank" rel="noreferrer">
                <Activity className="h-4 w-4" aria-hidden="true" /> API health
              </a>
            </div>
          </header>
          <div className="px-4 sm:px-8">{children}</div>
        </div>
      </body>
    </html>
  );
}
