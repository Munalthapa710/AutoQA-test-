import { cn } from "../lib/cn";

const toneByStatus: Record<string, string> = {
  queued: "bg-slate/10 text-slate",
  running: "bg-mist text-slate",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  passed: "bg-emerald-100 text-emerald-800",
  safe: "bg-emerald-100 text-emerald-800",
  risky: "bg-amber-100 text-amber-800",
  destructive: "bg-rose-100 text-rose-800",
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-emerald-100 text-emerald-800",
  accessibility: "bg-cyan-100 text-cyan-900",
  console: "bg-amber-100 text-amber-800",
  network: "bg-rose-100 text-rose-800",
  "confirmed issue": "bg-rose-100 text-rose-800",
  "likely bug": "bg-amber-100 text-amber-800",
  "needs review": "bg-slate/10 text-slate",
};

export function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  return (
    <span className={cn("inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em]", toneByStatus[normalized] ?? "bg-slate/10 text-slate")}>
      {value}
    </span>
  );
}
