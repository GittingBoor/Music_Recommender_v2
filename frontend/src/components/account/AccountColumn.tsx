import type { ReactNode } from "react";

/** Narrow single column shared by the account pages. */
export function AccountColumn({ title, children }: {
  readonly title: string;
  readonly children: ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">
        <div className="max-w-sm space-y-6">
          <h2 className="text-lg font-semibold leading-tight tracking-[-0.01em] text-ink stretch-semi">{title}</h2>
          {children}
        </div>
      </div>
    </div>
  );
}
