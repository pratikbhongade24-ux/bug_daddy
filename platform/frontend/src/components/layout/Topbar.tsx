import { useEffect, useState } from 'react';
import { LogOut, Cpu } from 'lucide-react';
import { Metric } from '../shared/Metric';

export function Topbar({
  stats,
  onLogout,
  onOpenCommandPalette,
  isAgentActive,
}: {
  stats: Record<string, number>;
  onLogout: () => void;
  onOpenCommandPalette?: () => void;
  isAgentActive?: boolean;
}) {
  const [clock, setClock] = useState('');

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString('en-IN', { hour12: false }));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="topbar">
      <div className="logo">
        <span className="logo-g">BUG</span> DADDY
      </div>
      <div className="tb-sep" />
      <div className="live-ind">
        <span className="live-dot" /> LIVE
      </div>

      {isAgentActive && (
        <div className="ai-active-badge">
          <span className="ai-active-badge-dot" />
          AI ACTIVE
        </div>
      )}

      <div className="tb-pills" role="status" aria-label="System metrics">
        <Metric label="Total" value={stats.total} />
        <Metric label="Critical" value={stats.critical} tone="red" />
        <Metric label="WIP" value={stats.wip} tone="amb" />
        <Metric label="Resolved" value={stats.resolved} tone="grn" />
      </div>

      <div className="tb-right">
        {/* ⌘K hint */}
        <button className="cmd-k-hint" onClick={onOpenCommandPalette} title="Open command palette">
          <Cpu size={11} />
          <kbd>⌘K</kbd>
        </button>

        <time className="tb-clock">{clock}</time>
        <button className="btn" onClick={onLogout} title="Logout">
          <LogOut size={14} /> Logout
        </button>
      </div>
    </header>
  );
}
