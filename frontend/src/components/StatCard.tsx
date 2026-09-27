/** One figure in a figure row: label above, number below, no box.
 *  Siblings are separated by a hairline — place several in a grid. */
export function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="py-3 pr-4 sm:[&:not(:first-child)]:border-l sm:[&:not(:first-child)]:pl-5 border-line">
      <p className="t-label">{label}</p>
      <p className="t-figure mt-2.5">{value}</p>
      {sub && <p className="font-mono text-2xs text-ink-3 mt-1.5">{sub}</p>}
    </div>
  );
}
