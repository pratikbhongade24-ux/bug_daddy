import clsx from 'clsx';
import { LayoutDashboard, Bug, ShieldCheck, Users, ScanSearch, BarChart2 } from 'lucide-react';
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
    <aside className="sidebar" aria-label="Primary">
      <div className="sb-sec">Navigation</div>
      <nav className="sidebar-nav">
        <button type="button" aria-current={view === 'dashboard' ? 'page' : undefined} className={clsx('nav-item', view === 'dashboard' && 'active')} onClick={() => setView('dashboard')}>
          <LayoutDashboard size={16} /> Dashboard <span className="ni-badge g">{stats.total}</span>
        </button>
        <button type="button" aria-current={view === 'issues' ? 'page' : undefined} className={clsx('nav-item', view === 'issues' && 'active')} onClick={() => setView('issues')}>
          <Bug size={16} /> Issues <span className="ni-badge r">{stats.backlog}</span>
        </button>
        <button type="button" aria-current={view === 'sonar' ? 'page' : undefined} className={clsx('nav-item', view === 'sonar' && 'active')} onClick={() => setView('sonar')}>
          <ShieldCheck size={16} /> SonarQube
        </button>
        <button type="button" aria-current={view === 'security' ? 'page' : undefined} className={clsx('nav-item', view === 'security' && 'active')} onClick={() => setView('security')}>
          <ScanSearch size={16} /> Security Scanner
        </button>
        <button type="button" aria-current={view === 'grafana' ? 'page' : undefined} className={clsx('nav-item', view === 'grafana' && 'active')} onClick={() => setView('grafana')}>
          <BarChart2 size={16} /> Grafana
        </button>
        {isAdmin ? (
          <button type="button" aria-current={view === 'admin' ? 'page' : undefined} className={clsx('nav-item', view === 'admin' && 'active')} onClick={() => setView('admin')}>
            <Users size={16} /> Admin
          </button>
        ) : null}
      </nav>
    </aside>
  );
}
