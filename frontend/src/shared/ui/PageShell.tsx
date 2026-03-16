import type { PropsWithChildren, ReactNode } from "react";

interface PageShellProps extends PropsWithChildren {
  title: string;
  description: string;
  actions?: ReactNode;
}

export function PageShell({ title, description, actions, children }: PageShellProps) {
  return (
    <section className="space-y-4">
      <div
        data-glass="true"
        className="relative overflow-hidden rounded-[calc(var(--radius)+10px)] border border-primary/20 bg-card/80 p-6 shadow-2xl backdrop-blur-xl sm:p-8"
      >
        <div className="pointer-events-none absolute right-0 top-0 h-56 w-56 translate-x-1/4 -translate-y-1/4 rounded-full bg-primary/15 blur-3xl" />
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/10" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <p className="compact-label">Интерфейс KT30</p>
            <div className="space-y-2">
              <h1 className="max-w-3xl text-4xl leading-none font-semibold sm:text-5xl">{title}</h1>
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground sm:text-[0.95rem]">{description}</p>
            </div>
          </div>
          {actions ? <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">{actions}</div> : null}
        </div>
      </div>
      <div className="grid gap-4">{children}</div>
    </section>
  );
}
