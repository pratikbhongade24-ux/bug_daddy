'use client';

import clsx from 'clsx';
import { useState } from 'react';
import { motion } from 'framer-motion';
import { Search, Download, ListFilter } from 'lucide-react';
import { Issue, IssueTab } from '@/lib/types';
import { PanelHeader } from '../shared/PanelHeader';
import { SkeletonTableRows } from '../shared/SkeletonLoader';

function issueStatusLabel(tab: IssueTab) {
  if (tab === 'wip') return 'Work in Progress';
  return tab.charAt(0).toUpperCase() + tab.slice(1);
}

export function IssuesView(props: {
  stats: Record<string, number>;
  tab: IssueTab;
  setTab: (tab: IssueTab) => void;
  search: string;
  setSearch: (value: string) => void;
  serviceFilter: string;
  setServiceFilter: (value: string) => void;
  criticalityFilter: string;
  setCriticalityFilter: (value: string) => void;
  originFilter: string;
  setOriginFilter: (value: string) => void;
  services: string[];
  issues: Issue[];
  loading: boolean;
  sortBy: (key: 'id' | 'freq') => void;
  prioritizeLoading: Record<number, string>;
  prioritize: (issue: Issue) => void;
  openGraph: (issue: Issue, summary: boolean) => void;
  onExport: () => void;
}) {
  const tabs: IssueTab[] = ['backlog', 'wip', 'review', 'resolved'];
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="view active">
      <PanelHeader
        title="Issue Workbench"
        subtitle="Search, route, and inspect issue execution"
        icon={<ListFilter size={18} />}
        actions={
          <button className="btn" onClick={props.onExport}>
            <Download size={14} /> Export CSV
          </button>
        }
      />
      <div className="table-controls">
        <div className="srch-box">
          <Search size={15} />
          <input value={props.search} onChange={(event) => props.setSearch(event.target.value)} placeholder="Search issue ID or description..." />
        </div>
        <select className="tc-sel" value={props.serviceFilter} onChange={(event) => props.setServiceFilter(event.target.value)}>
          <option value="">All Services</option>
          {props.services.map((service) => (
            <option key={service} value={service}>{service}</option>
          ))}
        </select>
        <select className="tc-sel" value={props.criticalityFilter} onChange={(event) => props.setCriticalityFilter(event.target.value)}>
          <option value="">All Criticality</option>
          <option>Critical</option>
          <option>High</option>
          <option>Medium</option>
          <option>Low</option>
        </select>
        <select className="tc-sel" value={props.originFilter} onChange={(event) => props.setOriginFilter(event.target.value)}>
          <option value="">All Origins</option>
          <option>CloudWatch</option>
          <option>CVE</option>
          <option>SonarQube</option>
          <option>JIRA</option>
        </select>
        <div className="tbl-count">
          {props.loading ? (
            <span style={{ color: 'var(--t3)', fontFamily: 'var(--mono)', fontSize: '0.8rem' }}>Loading…</span>
          ) : (
            <span><strong style={{ color: 'var(--t)' }}>{props.issues.length}</strong> issues</span>
          )}
        </div>
      </div>
      <div className="tabs">
        {tabs.map((tab) => (
          <button key={tab} className={clsx('tab', props.tab === tab && 'active')} onClick={() => props.setTab(tab)}>
            {issueStatusLabel(tab)} <span className="tc">{props.stats[tab]}</span>
          </button>
        ))}
      </div>
      <div className="table-wrap">
        {props.loading ? (
          <SkeletonTableRows count={6} />
        ) : (
          <table className="issues-table">
            <colgroup>
              <col className="col-id" />
              <col className="col-service" />
              <col className="col-error" />
              <col className="col-frequency" />
              <col className="col-criticality" />
              <col className="col-owner" />
              <col className="col-eta" />
              <col className="col-action" />
            </colgroup>
            <thead>
              <tr>
                <th onClick={() => props.sortBy('id')}>Issue ID</th>
                <th>Service</th>
                <th>Error</th>
                <th onClick={() => props.sortBy('freq')}>Frequency ↕</th>
                <th>Criticality</th>
                <th>Owner</th>
                <th>ETA</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {props.issues.map((issue) => (
                <IssueRow
                  key={issue.id}
                  issue={issue}
                  tab={props.tab}
                  loading={props.prioritizeLoading[issue.id]}
                  prioritize={props.prioritize}
                  openGraph={props.openGraph}
                />
              ))}
            </tbody>
          </table>
        )}
        {!props.loading && !props.issues.length ? (
          <div className="empty-state">No issues match the selected filters.</div>
        ) : null}
      </div>
    </motion.div>
  );
}

export function IssueRow({
  issue,
  tab,
  loading,
  prioritize,
  openGraph,
}: {
  issue: Issue;
  tab: IssueTab;
  loading?: string;
  prioritize: (issue: Issue) => void;
  openGraph: (issue: Issue, summary: boolean) => void;
}) {
  const [flashed, setFlashed] = useState(false);

  function handlePrioritize() {
    prioritize(issue);
    setTimeout(() => {
      setFlashed(true);
      setTimeout(() => setFlashed(false), 1600);
    }, 200);
  }

  return (
    <tr className={flashed ? 'row-flash' : ''}>
      <td className="td-id">{issue.id}</td>
      <td className="td-own">{issue.shortSvc}</td>
      <td className="td-desc" title={issue.err}>{issue.err}</td>
      <td>
        <span className={clsx('freq', issue.frequency > 400 ? 'hi' : issue.frequency > 100 ? 'med' : 'low')}>
          {issue.frequency}
        </span>
      </td>
      <td>
        <span className={clsx('badge', issue.criticality.toLowerCase())}>{issue.criticality}</span>
      </td>
      <td className="td-own">{issue.owner}</td>
      <td className="td-own">{issue.eta}</td>
      <td>
        {tab === 'backlog' ? (
          <button
            className={clsx('act-btn pri-btn', loading && 'loading')}
            disabled={Boolean(loading)}
            onClick={handlePrioritize}
            style={{ position: 'relative' }}
          >
            {loading ? '' : 'Invoke AI'}
          </button>
        ) : tab === 'resolved' ? (
          <button className="act-btn sum-btn" onClick={() => openGraph(issue, true)}>Summary</button>
        ) : (
          <button className="act-btn live-btn" onClick={() => openGraph(issue, false)}>
            {tab === 'review' ? 'Reviewing' : 'Live Graph'}
          </button>
        )}
      </td>
    </tr>
  );
}
