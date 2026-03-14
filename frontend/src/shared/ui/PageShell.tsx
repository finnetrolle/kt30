import type { PropsWithChildren, ReactNode } from "react";

interface PageShellProps extends PropsWithChildren {
  title: string;
  description: string;
  actions?: ReactNode;
}

export function PageShell({ title, description, actions, children }: PageShellProps) {
  return (
    <section className="page-shell">
      <div className="page-hero">
        <div>
          <p className="eyebrow">Standalone frontend</p>
          <h1>{title}</h1>
          <p className="page-description">{description}</p>
        </div>
        {actions ? <div className="page-actions">{actions}</div> : null}
      </div>
      <div className="page-grid">{children}</div>
    </section>
  );
}
