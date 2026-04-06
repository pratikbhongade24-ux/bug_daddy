export function MetricCard({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: string | number | null | undefined;
  accent: string;
  hint: string;
}) {
  return (
    <div className="metric-card" style={{ ["--metric-accent" as string]: accent }}>
      <span className="metric-card__label">{label}</span>
      <strong className="metric-card__value">{value ?? "—"}</strong>
      <span className="metric-card__hint">{hint}</span>
    </div>
  );
}
