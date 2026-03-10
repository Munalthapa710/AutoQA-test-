import { cn } from "../lib/cn";

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-[28px] border border-slate/10 bg-white/85 p-6 shadow-pane backdrop-blur", className)}>
      {children}
    </section>
  );
}
