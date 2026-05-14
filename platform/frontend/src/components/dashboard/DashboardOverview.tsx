import clsx from 'clsx';
import { Download, Zap, Gauge, Activity } from 'lucide-react';
import { DashboardCharts, Issue, FeedItem, ViewName, ToastKind } from '@/lib/types';
import { PanelHeader } from '../shared/PanelHeader';
import { Kpi } from './Kpi';
import { HorizontalChart } from './HorizontalChart';
import { SpotlightCard } from '../shared/SpotlightCard';
import { SkeletonKpiGrid } from '../shared/SkeletonLoader';
import { motion } from 'framer-motion';

export function DashboardOverview({
  stats,
  charts,
  issues,
  feed,
  onExport,
  onEscalate,
  setView,
  setServiceFilter,
  openGraph,
  toast,
  loading,
}: {
  stats: Record<string, number>;
  charts: DashboardCharts;
  issues: Issue[];
  feed: FeedItem[];
  onExport: () => void;
  onEscalate: () => void;
  setView: (view: ViewName) => void;
  setServiceFilter: (service: string) => void;
  openGraph: (issue: Issue, summary: boolean) => void;
  toast: (message: string, kind?: ToastKind) => void;
  loading?: boolean;
}) {
  const escalation = issues
    .filter((issue) => issue.frequency > 400 && issue.status !== 'resolved')
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 8);

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="view active">
      <PanelHeader
        title="Command Center"
        subtitle="Live agentic issue intelligence"
        icon={<Gauge size={18} />}
        actions={
          <>
            <button className="btn" onClick={onExport}>
              <Download size={14} /> Export CSV
            </button>
            <button className="btn danger" onClick={onEscalate}>
              <Zap size={14} /> Escalate All Critical
            </button>
          </>
        }
      />
      <div className="dash-scroll">
        {loading ? (
          <SkeletonKpiGrid />
        ) : (
          <div className="kpi-grid animate-enter stagger-1">
            <Kpi label="Total Issues" value={stats.total} color="var(--c3)" onClick={() => setView('issues')} />
            <Kpi label="Critical" value={stats.critical} color="var(--c2)" onClick={() => setView('issues')} />
            <Kpi label="Work In Progress" value={stats.wip} color="var(--c4)" onClick={() => setView('issues')} />
            <Kpi label="Resolved" value={stats.resolved} color="var(--c1)" onClick={() => setView('issues')} />
          </div>
        )}
        <div className="sec-label animate-enter stagger-2">Service Distribution</div>
        <div className="hcharts-grid animate-enter stagger-3">
          <HorizontalChart
            title="Backlog by Service"
            rows={charts.services.map((row) => ({ label: row.service_name, value: Number(row.backlog || 0), service: row.service_name }))}
            onService={(service) => {
              setServiceFilter(service);
              setView('issues');
            }}
          />
          <HorizontalChart
            title="WIP by Service"
            rows={charts.services.map((row) => ({ label: row.service_name, value: Number(row.wip || 0), service: row.service_name }))}
            onService={(service) => {
              setServiceFilter(service);
              setView('issues');
            }}
          />
        </div>
        <div className="bottom-row animate-enter stagger-4">
          <SpotlightCard className="esc-card" spotlightColor="rgba(239, 68, 68, 0.05)">
            <div className="esc-card-head">
              <div>
                <div className="esc-head-title">Escalation Queue</div>
                <div className="esc-head-sub">High frequency unresolved issues</div>
              </div>
              <div className="esc-count-badge">{escalation.length}</div>
            </div>
            <div className="esc-list">
              {escalation.map((issue) => (
                <button
                  key={issue.id}
                  className={clsx('esc-item', issue.criticality === 'Critical' && 'critical-glow')}
                  onClick={() => openGraph(issue, issue.tab === 'resolved')}
                >
                  <span className="esc-severity" />
                  <span className="esc-content">
                    <strong>{issue.shortSvc}</strong>
                    <em>{issue.err}</em>
                  </span>
                  <span className="esc-right">
                    <b>{issue.frequency}</b>
                    <small>{issue.eta}</small>
                  </span>
                </button>
              ))}
              {!escalation.length ? <div className="empty-state">No critical escalations.</div> : null}
            </div>
          </SpotlightCard>
          <SpotlightCard className="feed-card" spotlightColor="rgba(59, 130, 246, 0.05)">
            <div className="esc-card-head">
              <div>
                <div className="esc-head-title">Live Feed</div>
                <div className="esc-head-sub">Latest platform events</div>
              </div>
            </div>
            <div className="feed-list">
              {feed.map((item, idx) => (
                <button key={`${item.id}-${item.event_type}`} className={clsx('feed-item', idx === 0 && 'new')} onClick={() => toast(item.title, 'inf')}>
                  <Activity size={15} />
                  <span>
                    <strong>{item.title}</strong>
                    <em>{item.meta}</em>
                  </span>
                </button>
              ))}
              {!feed.length ? <div className="empty-state">No feed events.</div> : null}
            </div>
          </SpotlightCard>
        </div>
      </div>
    </motion.div>
  );
}
