'use client';

import React, { useEffect, useRef } from 'react';
import { useMotionValue, animate } from 'framer-motion';
import { SpotlightCard } from '../shared/SpotlightCard';

// Mini sparkline SVG — generates a soft random waveform
function Sparkline({ color }: { color: string }) {
  const points = [4, 7, 5, 9, 6, 8, 10, 7, 9, 6, 8, 11, 9, 10];
  const max = Math.max(...points);
  const min = Math.min(...points);
  const h = 24;
  const w = 72;
  const pts = points.map((v, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - ((v - min) / (max - min + 1)) * h;
    return `${x},${y}`;
  });
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.5"
      />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r="3" fill={color} opacity="0.7" />
    </svg>
  );
}

function AnimatedNumber({ value }: { value: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const motionVal = useMotionValue(0);

  useEffect(() => {
    const controls = animate(motionVal, value, {
      duration: 1.2,
      ease: [0.2, 0.8, 0.2, 1],
    });
    return controls.stop;
  }, [motionVal, value]);

  useEffect(() => {
    return motionVal.on('change', (v) => {
      if (ref.current) ref.current.textContent = Math.round(v).toString();
    });
  }, [motionVal]);

  return <span ref={ref}>0</span>;
}

export function Kpi({
  label,
  value,
  color,
  onClick,
}: {
  label: string;
  value: number;
  color: string;
  onClick: () => void;
}) {
  return (
    <SpotlightCard
      className="kpi-card"
      style={{ '--kc': color } as React.CSSProperties}
      onClick={onClick}
      spotlightColor={color.replace('var(', 'color-mix(in srgb, var(').replace(')', '), transparent 90%)')}
    >
      <div className="kpi-label">{label}</div>
      <div className="kpi-val">
        <AnimatedNumber value={value} />
      </div>
      <div className="kpi-footer">
        <Sparkline color={color.replace('var(', 'var(').replace(')', ')')} />
        <span className="kpi-trend up" style={{ borderColor: color, color: color, background: `color-mix(in srgb, ${color} 10%, transparent)` }}>
          LIVE
        </span>
      </div>
    </SpotlightCard>
  );
}
