import { cn } from "../lib/cn";

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("min-w-0 rounded-2xl border border-slate/15 bg-white p-4 shadow-sm sm:p-6", className)}>
      {children}
    </section>
  );
}
