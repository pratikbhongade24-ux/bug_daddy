import clsx from 'clsx';

export function Metric({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="tb-pill">
      <div className={clsx('tb-pill-val', tone)}>{value}</div>
      <div className="tb-pill-lbl">{label}</div>
    </div>
  );
}
