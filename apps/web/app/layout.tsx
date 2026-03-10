import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoQA Agent",
  description: "Automated QA dashboard for page discovery, form submission coverage, and bug handoff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="page-grid min-h-screen bg-grid px-4 pb-10 pt-6 sm:px-8">
          <header className="mx-auto mb-8 flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 rounded-[28px] border border-slate/10 bg-white/80 px-5 py-4 shadow-pane backdrop-blur">
            <div>
              <Link href="/" className="font-display text-2xl font-semibold tracking-tight text-ink">
                AutoQA Agent
              </Link>
              <p className="mt-1 text-sm text-slate/70">Explore menus, exercise forms, and hand testers readable bug evidence.</p>
            </div>
            <nav className="flex items-center gap-4 text-sm font-medium text-slate/80">
              <Link href="/">Dashboard</Link>
              <a href="http://localhost:8000/health" target="_blank" rel="noreferrer">
                API Health
              </a>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
