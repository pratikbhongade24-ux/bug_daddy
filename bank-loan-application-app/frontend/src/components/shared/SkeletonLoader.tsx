import React from 'react';

export function SkeletonKpiGrid() {
  return (
    <div className="skeleton-kpi-grid">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="skeleton skeleton-kpi" style={{ animationDelay: `${i * 0.1}s` }} />
      ))}
    </div>
  );
}

export function SkeletonTableRows({ count = 5 }: { count?: number }) {
  return (
    <div style={{ padding: '1rem 1.5rem' }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton skeleton-row" style={{ animationDelay: `${i * 0.08}s` }} />
      ))}
    </div>
  );
}

export function SkeletonText({ width = '100%', height = 14, style }: { width?: string | number; height?: number; style?: React.CSSProperties }) {
  return (
    <div
      className="skeleton skeleton-text"
      style={{ width, height, ...style }}
    />
  );
}
