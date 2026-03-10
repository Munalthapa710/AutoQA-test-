"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, FileCode2 } from "lucide-react";

import { api, generatedTestFileUrl } from "../lib/api";
import type { GeneratedTest } from "../lib/types";
import { Panel } from "./panel";

export function GeneratedTestViewer({ testId }: { testId: string }) {
  const [test, setTest] = useState<GeneratedTest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api
      .getGeneratedTest(testId)
      .then((data) => {
        if (active) {
          setTest(data);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load generated test.");
        }
      });

    return () => {
      active = false;
    };
  }, [testId]);

  if (error) {
    return (
      <main className="mx-auto max-w-7xl">
        <Panel>
          <p className="text-sm text-rose-700">{error}</p>
        </Panel>
      </main>
    );
  }

  if (!test) {
    return (
      <main className="mx-auto max-w-7xl">
        <Panel>
          <p className="text-sm text-slate/70">Loading generated test...</p>
        </Panel>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-ink p-3 text-white">
              <FileCode2 className="h-5 w-5" />
            </div>
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.34em] text-slate/60">Generated Playwright spec</p>
              <h1 className="mt-2 font-display text-3xl font-semibold text-ink">{test.name}</h1>
              <p className="mt-1 text-sm text-slate/70">{test.file_path}</p>
            </div>
          </div>
          <div className="flex gap-3">
            <a href={generatedTestFileUrl(test.file_path)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-3 text-sm font-semibold text-white">
              Download file
              <Download className="h-4 w-4" />
            </a>
            <Link href={`/runs/${test.run_id}`} className="inline-flex items-center gap-2 rounded-full border border-slate/10 bg-white px-5 py-3 text-sm font-semibold text-slate">
              Back to run
            </Link>
          </div>
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <pre className="overflow-x-auto rounded-[24px] bg-ink p-6 font-mono text-sm leading-7 text-sand">{test.content}</pre>
      </Panel>
    </main>
  );
}
