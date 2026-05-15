import { SpotlightCard } from '../shared/SpotlightCard';

const chartColors = ['var(--c3)', 'var(--c1)', 'var(--c4)', 'var(--c5)', 'var(--c6)', 'var(--c2)'];

export function HorizontalChart({ title, rows, onService }: { title: string; rows: { label: string; value: number; service: string }[]; onService: (service: string) => void }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  const visibleRows = rows.filter((row) => row.value > 0).slice(0, 7);
  return (
    <SpotlightCard className="hchart-card" spotlightColor="rgba(59, 130, 246, 0.05)">
      <div className="hcc-header">
        <div>
          <div className="hcc-title">{title}</div>
          <div className="hcc-sub">Highest volume services</div>
        </div>
        <div className="hcc-total">{total} total</div>
      </div>
      <div className="hbar-chart">
        {visibleRows.map((row, index) => {
          const percent = total ? Math.round((row.value / total) * 100) : 0;
          return (
            <button key={row.service} className="hbc-row" onClick={() => onService(row.service)}>
              <span className="hbc-rank">{String(index + 1).padStart(2, '0')}</span>
              <span className="hbc-main">
                <span className="hbc-meta">
                  <span className="hbc-label">{row.label.replace('grabhack-', '')}</span>
                  <span className="hbc-val">{row.value} issues</span>
                </span>
                <span className="hbc-track" data-tip={row.value}>
                  <span
                    className="hbc-fill"
                    style={{ width: `${Math.max((row.value / max) * 100, 4)}%`, background: chartColors[index % chartColors.length] }}
                  />
                </span>
              </span>
              <span className="hbc-pct">{percent}%</span>
            </button>
          );
        })}
        {!visibleRows.length ? <div className="chart-empty">No active issues for this state.</div> : null}
      </div>
    </SpotlightCard>
  );
}
