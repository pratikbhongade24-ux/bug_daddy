import React from 'react';
import { SpotlightCard } from '../shared/SpotlightCard';

const chartColors = ['var(--c3)', 'var(--c1)', 'var(--c4)', 'var(--c5)', 'var(--c6)', 'var(--c2)'];

export function HorizontalChart({ title, rows, onService }: { title: string; rows: { label: string; value: number; service: string }[]; onService: (service: string) => void }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <SpotlightCard className="hchart-card" spotlightColor="rgba(59, 130, 246, 0.05)">
      <div className="hcc-header">
        <div className="hcc-title">{title}</div>
        <div className="hcc-total">{rows.reduce((sum, row) => sum + row.value, 0)} total</div>
      </div>
      <div className="hbar-chart">
        {rows.map((row, index) => (
          <button key={row.service} className="hbc-row" onClick={() => onService(row.service)}>
            <span className="hbc-label">{row.label.replace('grabhack-', '')}</span>
            <span className="hbc-track" data-tip={row.value}>
              <span className="hbc-fill" style={{ width: `${(row.value / max) * 100}%`, background: chartColors[index % chartColors.length] }} />
            </span>
            <span className="hbc-val">{row.value}</span>
          </button>
        ))}
      </div>
    </SpotlightCard>
  );
}
