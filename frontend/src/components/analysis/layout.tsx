import { COLOR } from "../../theme";
import { Link } from "../../router";

/** A page section: heading in a narrow left column, content on the right.
 *  Sections are divided by a rule, not boxed. */
export function Section({ title, note, children }: {
  title: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid grid-cols-1 lg:grid-cols-[168px_1fr] gap-x-10 gap-y-4 border-t border-line-strong pt-5">
      <div className="lg:sticky lg:top-5 self-start">
        <h2 className="t-section">{title}</h2>
        {note && <p className="text-xs text-ink-3 mt-1.5 leading-relaxed">{note}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

/** One chart with its caption. No frame — the caption and spacing group it. */
export function Figure({ title, note, children, className = "" }: {
  title: string;
  note?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <figure className={`min-w-0 ${className}`}>
      <figcaption className="mb-3 flex items-baseline gap-2 flex-wrap">
        <span className="text-sm font-medium text-ink">{title}</span>
        {note && <span className="t-label">{note}</span>}
      </figcaption>
      {children}
    </figure>
  );
}

export interface RankedRow {
  label: string;
  value: number;
  /** Identity colour; single-series lists leave it out. */
  color?: string;
  /** Where a click on the row leads (the songs behind it). */
  to?: string;
}

const ROW_CLASS = "grid items-center gap-3 h-[22px] break-inside-avoid";

/** Label · bar · value, one row per item. The value is always printed,
 *  so the bars need no axis and no tooltip. */
export function RankedBars({ rows, format = (v) => String(v), labelWidth = 128, valueWidth = 44, max, className = "" }: {
  rows: RankedRow[];
  format?: (v: number) => string;
  labelWidth?: number;
  valueWidth?: number;
  /** Scale maximum; defaults to the largest value. */
  max?: number;
  className?: string;
}) {
  const top = max ?? Math.max(1e-9, ...rows.map((r) => r.value));
  return (
    <div className={className}>
      {rows.map((r) => {
        const style = { gridTemplateColumns: `${labelWidth}px 1fr ${valueWidth}px` };
        const cells = (
          <>
            <span className="text-xs text-ink-2 truncate" title={r.label}>{r.label}</span>
            <div className="h-2.5">
              <div
                className="h-full"
                style={{
                  width: `${Math.max(0, Math.min(1, r.value / top)) * 100}%`,
                  minWidth: r.value > 0 ? 2 : 0,
                  background: r.color ?? COLOR.data,
                }}
              />
            </div>
            <span className="font-mono text-2xs text-ink-3 text-right tabular-nums whitespace-nowrap">{format(r.value)}</span>
          </>
        );
        return r.to ? (
          <Link
            key={r.label}
            to={r.to}
            className={`${ROW_CLASS} chart-link`}
            style={style}
            title={`Show the songs: ${r.label}`}
          >
            {cells}
          </Link>
        ) : (
          <div key={r.label} className={ROW_CLASS} style={style}>{cells}</div>
        );
      })}
    </div>
  );
}
