import clsx from 'clsx';
import { LayoutDashboard, Bug, ShieldCheck, Users, ScanSearch } from 'lucide-react';
import { ViewName } from '@/lib/types';

export function Sidebar({
  view,
  setView,
  isAdmin,
  stats,
}: {
  view: ViewName;
  setView: (view: ViewName) => void;
  isAdmin: boolean;
  stats: Record<string, number>;
}) {
  return (
    <aside className="sidebar">
      <div className="sb-sec">Navigation</div>
      <button className={clsx('nav-item', view === 'dashboard' && 'active')} onClick={() => setView('dashboard')}>
        <LayoutDashboard size={16} /> Dashboard <span className="ni-badge g">{stats.total}</span>
      </button>
      <button className={clsx('nav-item', view === 'issues' && 'active')} onClick={() => setView('issues')}>
        <Bug size={16} /> Issues <span className="ni-badge r">{stats.backlog}</span>
      </button>
      <button className={clsx('nav-item', view === 'sonar' && 'active')} onClick={() => setView('sonar')}>
        <ShieldCheck size={16} /> SonarQube
      </button>
      <button className={clsx('nav-item', view === 'security' && 'active')} onClick={() => setView('security')}>
        <ScanSearch size={16} /> Security Scanner
      </button>
      {isAdmin ? (
        <button className={clsx('nav-item', view === 'admin' && 'active')} onClick={() => setView('admin')}>
          <Users size={16} /> Admin
        </button>
      ) : null}
      <div className="sb-filters">
        <div className="sec-label">Runtime</div>
        <div className="health-card">
          <span>Bug Daddy</span>
          <strong>Idle</strong>
          <div className="hbar">
            <div className="hbar-f" style={{ width: '8%', background: 'var(--c3)' }} />
          </div>
        </div>
        <div className="health-card">
          <span>Incident Daddy</span>
          <strong>Ready</strong>
          <div className="hbar">
            <div className="hbar-f" style={{ width: '62%', background: 'var(--c1)' }} />
          </div>
        </div>
        <div className="health-card">
          <span>Reviewer Daddy</span>
          <strong>Ready</strong>
          <div className="hbar">
            <div className="hbar-f" style={{ width: '45%', background: 'var(--c5)' }} />
          </div>
        </div>
      </div>
    </aside>
  );
}
