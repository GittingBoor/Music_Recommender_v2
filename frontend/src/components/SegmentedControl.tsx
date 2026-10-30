export interface Segment<T extends string> {
  readonly id: T;
  readonly label: string;
  /** Shown next to the label; left out when undefined. */
  readonly count?: number;
  readonly disabled?: boolean;
}

/** Touch-sized `.seg` switch with counts: 40px high below lg, the usual height above. */
export function SegmentedControl<T extends string>({ label, segments, value, onChange, className = "" }: {
  readonly label: string;
  readonly segments: readonly Segment<T>[];
  readonly value: T;
  readonly onChange: (id: T) => void;
  readonly className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={`seg ${className}`}>
      {segments.map((s) => (
        <button
          key={s.id}
          type="button"
          aria-pressed={s.id === value}
          disabled={s.disabled}
          onClick={() => onChange(s.id)}
          className={`
            seg-item h-10 flex-auto px-1.5 disabled:pointer-events-none disabled:opacity-40 lg:h-7 lg:px-2.5
            ${s.id === value ? "seg-item-on" : ""}
          `}
        >
          {s.label}
          {s.count !== undefined && (
            <span className="ml-1 font-mono text-2xs tabular-nums opacity-70">{s.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
