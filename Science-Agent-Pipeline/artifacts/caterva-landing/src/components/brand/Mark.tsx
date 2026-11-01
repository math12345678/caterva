/**
 * The caterva mark: a C of eight dots, seven ink and one signal.
 *
 * Geometry is measured from the master artwork (docs/brand/caterva-mark.svg);
 * do not redraw it by eye. Ink follows `currentColor`, so the mark takes the
 * text colour of wherever it sits, and the signal dot follows `--signal`, so
 * on an ink slab both flip together.
 */
const DOTS: ReadonlyArray<readonly [number, number, number, boolean]> = [
  [541.3, 242.6, 61.7, false],
  [386.5, 281.7, 44.2, false],
  [688.7, 309.3, 50.9, true],
  [305.1, 403.8, 59.6, false],
  [297.4, 569.0, 44.2, false],
  [382.6, 697.4, 60.2, false],
  [680.8, 684.5, 44.2, false],
  [542.5, 744.6, 53.5, false],
];

export function Mark({
  size = 20,
  className = "",
  title,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="236 172 514 634"
      height={size}
      width={(size * 514) / 634}
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {DOTS.map(([cx, cy, r, signal]) => (
        <circle
          key={`${cx}-${cy}`}
          cx={cx}
          cy={cy}
          r={r}
          fill={signal ? "var(--signal)" : "currentColor"}
        />
      ))}
    </svg>
  );
}

/** Mark and wordmark, set as in the master lockup. */
export function Lockup({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center ${className}`} style={{ gap: size * 0.55 }}>
      <Mark size={size} />
      <span className="wordmark leading-none" style={{ fontSize: size * 0.72 }}>
        caterva
      </span>
    </span>
  );
}
