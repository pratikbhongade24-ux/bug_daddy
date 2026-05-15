import React, { MouseEvent, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { GitBranch, X, Cloud, FlaskConical, ShieldCheck, ClipboardList, Database, Zap, ClipboardPenLine, Siren, Brain, Bug, Search, Target, Bot, Code2, GitPullRequest, HardHat, CircleHelp, MessageCircle } from 'lucide-react';
import { apiJson } from '@/lib/api';
import { Issue, ExecutionEvent, WorkflowNode, WorkflowEdge, WorkflowGraph, ListResponse } from '@/lib/types';

// Graph utilities from DashboardApp.tsx
const archNodes: WorkflowNode[] = [
  { id: 'cw', x: 100, y: 20, icon: 'CW', label: 'CloudWatch', sub: 'Microservices', color: 'var(--c6)', type: 'trigger' },
  { id: 'sq', x: 250, y: 20, icon: 'SQ', label: 'SonarQube', sub: 'Code Quality', color: 'var(--c3)', type: 'trigger' },
  { id: 'cve', x: 400, y: 20, icon: 'CV', label: 'CVE Monitor', sub: 'Security', color: 'var(--c6)', type: 'trigger' },
  { id: 'jira', x: 550, y: 20, icon: 'JR', label: 'JIRA Backlogs', sub: 'Tech Debt', color: 'var(--c5)', type: 'trigger' },
  { id: 'slk', x: 700, y: 20, icon: 'SL', label: 'Slack Incident', sub: 'Communication', color: 'var(--c3)', type: 'trigger' },
  { id: 'db', x: 380, y: 120, icon: 'DB', label: 'Issues Tracker', sub: 'PostgreSQL', color: 'var(--c1)', type: 'agent' },
  { id: 'esc', x: 380, y: 220, icon: 'ES', label: 'Escalation Agent', sub: 'triage + route', color: 'var(--c3)', type: 'agent' },
  { id: 'jag', x: 580, y: 220, icon: 'JA', label: 'Jira Agent', sub: 'Jira Update', color: 'var(--c5)', type: 'agent' },
  { id: 'inc', x: 110, y: 385, icon: 'ID', label: 'Incident Daddy', sub: 'Orchestrator', color: 'var(--c2)', type: 'daddy' },
  { id: 'sme', x: 310, y: 390, icon: 'SM', label: 'SME', sub: 'Knowledge Base', color: 'var(--c4)', type: 'agent' },
  { id: 'bug', x: 700, y: 310, icon: 'BD', label: 'Bug Daddy', sub: 'Orchestrator', color: 'var(--c1)', type: 'daddy' },
  { id: 'ctx', x: 760, y: 455, icon: 'CX', label: 'Context Analyser', sub: 'Analysis', color: 'var(--c4)', type: 'agent' },
  { id: 'crit_ctx', x: 760, y: 595, icon: 'CC', label: 'Context Critique', sub: 'Review Analysis', color: 'var(--c6)', type: 'agent' },
  { id: 'strat', x: 560, y: 455, icon: 'PL', label: 'Planner', sub: 'Plan', color: 'var(--c3)', type: 'agent' },
  { id: 'crit_strat', x: 560, y: 595, icon: 'PC', label: 'Planner Critique', sub: 'Review Plan', color: 'var(--c6)', type: 'agent' },
  { id: 'code', x: 960, y: 455, icon: 'CD', label: 'Coder', sub: 'Write Fix', color: 'var(--c1)', type: 'agent' },
  { id: 'crit_code', x: 910, y: 595, icon: 'RC', label: 'Coder Critique', sub: 'Review Code', color: 'var(--c6)', type: 'agent' },
  { id: 'jprf', x: 1060, y: 595, icon: 'GH', label: 'GitHub', sub: 'Pull Request', color: 'var(--c3)', type: 'agent' },
  { id: 'rev', x: 1240, y: 310, icon: 'RD', label: 'Reviewer Daddy', sub: 'AI Reviewer', color: 'var(--c5)', type: 'daddy' },
];

const archEdges: WorkflowEdge[] = [
  ['cw', 'db'],
  ['sq', 'db'],
  ['cve', 'db'],
  ['jira', 'db'],
  ['slk', 'db'],
  ['db', 'esc'],
  ['esc', 'jag'],
  ['esc', 'inc'],
  ['esc', 'bug'],
  ['bug', 'sme'],
  ['bug', 'strat'],
  ['strat', 'crit_strat'],
  ['crit_strat', 'strat'],
  ['bug', 'ctx'],
  ['ctx', 'crit_ctx'],
  ['crit_ctx', 'ctx'],
  ['bug', 'code'],
  ['code', 'crit_code'],
  ['crit_code', 'code'],
  ['code', 'jprf'],
  ['bug', 'rev'],
];

const nodeStyleById = Object.fromEntries(archNodes.map((node) => [node.id, { ...node }]));
const nodeAliases: Record<string, string> = { crit1: 'crit_strat', crit2: 'crit_code', airev: 'rev', jrf: 'jag' };

function normalizeEdge(edge: WorkflowEdge): [string, string] { return Array.isArray(edge) ? [edge[0], edge[1]] : [edge.from, edge.to]; }
function canonicalNodeId(id: string | undefined) { if (!id) return ''; return nodeAliases[id] || id; }
function uniqueEdges(edges: [string, string][]) {
  const seen = new Set<string>();
  return edges.filter(([from, to]) => { const key = `${from}-${to}`; if (seen.has(key)) return false; seen.add(key); return true; });
}
function normalizeNodeType(type: string | undefined) {
  if (type === 'agent' || type === 'daddy' || type === 'trigger' || type === 'tool' || type === 'store' || type === 'output') return type;
  return 'agent';
}

function nodeColor(node: WorkflowNode) {
  if (node.color) return node.color;
  const id = node.id.toLowerCase();
  if (id.includes('inc')) return 'var(--c2)';
  if (id.includes('bug') || id.includes('code')) return 'var(--c1)';
  if (id.includes('sme') || id.includes('ctx')) return 'var(--c4)';
  if (id.includes('rev') || id.includes('jira')) return 'var(--c5)';
  if (id.includes('cve') || id.includes('crit')) return 'var(--c6)';
  return 'var(--c3)';
}

function nodeIcon(node: WorkflowNode) {
  if (node.icon) return node.icon;
  const label = `${node.id} ${node.label}`.toLowerCase();
  if (label.includes('cloud')) return 'CL';
  if (label.includes('sonar')) return 'SQ';
  if (label.includes('cve')) return 'CV';
  if (label.includes('jira')) return 'JR';
  if (label.includes('slack')) return 'SL';
  if (label.includes('incident')) return 'IN';
  if (label.includes('bug')) return 'BD';
  if (label.includes('sme')) return 'SM';
  if (label.includes('code')) return 'CD';
  if (label.includes('review')) return 'RV';
  return 'AG';
}

function renderNodeIcon(node: WorkflowNode) {
  const iconProps = { size: node.type === 'daddy' ? 22 : 17, strokeWidth: 2.2 };
  switch (canonicalNodeId(node.id)) {
    case 'cw': return <Cloud {...iconProps} />;
    case 'sq': return <FlaskConical {...iconProps} />;
    case 'cve': return <ShieldCheck {...iconProps} />;
    case 'jira': return <ClipboardList {...iconProps} />;
    case 'slk': return <MessageCircle size={17} strokeWidth={2.2} />;
    case 'db': return <Database {...iconProps} />;
    case 'esc': return <Zap {...iconProps} />;
    case 'jag': return <ClipboardPenLine {...iconProps} />;
    case 'inc': return <Siren {...iconProps} />;
    case 'sme': return <Brain {...iconProps} />;
    case 'bug': return <Bug {...iconProps} />;
    case 'ctx': return <Search {...iconProps} />;
    case 'crit_ctx':
    case 'crit_strat':
    case 'crit_code': return <Target {...iconProps} />;
    case 'strat': return <Bot {...iconProps} />;
    case 'code': return <Code2 {...iconProps} />;
    case 'jprf': return <GitPullRequest {...iconProps} />;
    case 'rev': return <HardHat {...iconProps} />;
    default: return node.icon ? <span className="nd-icon-text">{node.icon}</span> : <CircleHelp {...iconProps} />;
  }
}

function normalizeNodeModel(node: WorkflowNode): WorkflowNode {
  const id = canonicalNodeId(node.id);
  const style = nodeStyleById[id];
  return {
    ...node, ...style, id, type: normalizeNodeType(style?.type || node.type),
    icon: style?.icon || node.icon || nodeIcon({ ...node, id }), color: style?.color || node.color || nodeColor({ ...node, id }),
    sub: style?.sub || node.sub, x: Number.isFinite(Number(style?.x)) ? Number(style?.x) : Number(node.x || 0),
    y: Number.isFinite(Number(style?.y)) ? Number(style?.y) : Number(node.y || 0),
  };
}

function normalizeWorkflowGraph(graph: WorkflowGraph | undefined): WorkflowGraph {
  const rawNodes = Array.isArray(graph?.nodes) ? graph.nodes : archNodes;
  const rawEdges = Array.isArray(graph?.edges) ? graph.edges : archEdges;
  const architectureGraph = rawNodes.some((node) => ['esc', 'db', 'bug', 'inc', 'rev'].includes(canonicalNodeId(node.id)));
  if (architectureGraph) {
    const rawById = new Map(rawNodes.map((node) => [canonicalNodeId(node.id), node]));
    const nodes = archNodes.map((style) => normalizeNodeModel({ ...rawById.get(style.id), ...style }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = archEdges.map(normalizeEdge).filter(([from, to]) => nodeIds.has(from) && nodeIds.has(to));
    return { nodes, edges: uniqueEdges(edges) };
  }
  const nodes = rawNodes.map(normalizeNodeModel);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = rawEdges.map(normalizeEdge).map(([from, to]) => [canonicalNodeId(from), canonicalNodeId(to)] as [string, string]).filter(([from, to]) => nodeIds.has(from) && nodeIds.has(to));
  return { nodes, edges: uniqueEdges(edges) };
}

function getNodeSize(node: WorkflowNode) {
  if (node.type === 'agent' || node.type === 'tool' || node.type === 'store') return { w: 140, h: 44 };
  if (node.type === 'daddy') return { w: 58, h: 58 };
  return { w: 52, h: 52 };
}

function getNodeCenter(node: WorkflowNode) {
  const size = getNodeSize(node);
  return { x: node.x + size.w / 2, y: node.y + size.h / 2 };
}

function edgePath(from: WorkflowNode, to: WorkflowNode, allEdges: [string, string][]) {
  const fromCenter = getNodeCenter(from);
  const toCenter = getNodeCenter(to);
  const fromSize = getNodeSize(from);
  const toSize = getNodeSize(to);
  const dx = toCenter.x - fromCenter.x;
  const dy = toCenter.y - fromCenter.y;
  let x1: number; let y1: number; let x2: number; let y2: number;
  if (Math.abs(dy) > Math.abs(dx) * 0.6) {
    x1 = fromCenter.x; y1 = fromCenter.y + (dy > 0 ? fromSize.h / 2 : -fromSize.h / 2);
    x2 = toCenter.x; y2 = toCenter.y + (dy > 0 ? -toSize.h / 2 : toSize.h / 2);
  } else {
    x1 = fromCenter.x + (dx > 0 ? fromSize.w / 2 : -fromSize.w / 2); y1 = fromCenter.y;
    x2 = toCenter.x + (dx > 0 ? -toSize.w / 2 : toSize.w / 2); y2 = toCenter.y;
  }
  let cpx1 = x1; let cpx2 = x2; let cpy1 = y1 + (y2 - y1) * 0.4; let cpy2 = y1 + (y2 - y1) * 0.6;
  const hasReturnEdge = allEdges.some(([candidateFrom, candidateTo]) => candidateFrom === to.id && candidateTo === from.id);
  if (hasReturnEdge) {
    const offset = from.id < to.id ? -18 : 18;
    if (Math.abs(dy) > Math.abs(dx) * 0.6) { cpx1 += offset; cpx2 += offset; } else { cpy1 += offset; cpy2 += offset; }
  }
  return `M${x1},${y1} C${cpx1},${cpy1} ${cpx2},${cpy2} ${x2},${y2}`;
}

function activePathForWorkflow(workflowKey: string) {
  return workflowKey === 'incident_daddy' ? ['db', 'esc', 'jag', 'inc'] : ['db', 'esc', 'jag', 'bug', 'sme', 'strat', 'crit_strat', 'ctx', 'crit_ctx', 'code', 'crit_code', 'jprf', 'rev'];
}

function initialGraphNodeStates(workflowKey: string, isSummary: boolean) {
  const triggerStates = Object.fromEntries(['cw', 'sq', 'cve', 'jira', 'slk'].map((id) => [id, 'done']));
  if (!isSummary) return triggerStates;
  return { ...triggerStates, ...Object.fromEntries(activePathForWorkflow(workflowKey).map((id) => [id, 'done'])) };
}

// Components
function GroupBox({ label, x, y, w, h, color }: { label: string; x: number; y: number; w: number; h: number; color: string }) {
  return <div className="group-box" style={{ left: x, top: y, width: w, height: h, '--group-color': color } as React.CSSProperties}><span>{label}</span></div>;
}

function GraphNode({ node, state }: { node: WorkflowNode; state?: string }) {
  const color = nodeColor(node);
  const isAgent = node.type === 'agent' || node.type === 'tool' || node.type === 'store';
  const ring = isAgent ? { vb: '0 0 140 44', cx: 70, cy: 22, r: 70 } : node.type === 'daddy' ? { vb: '0 0 82 82', cx: 41, cy: 41, r: 38 } : { vb: '0 0 82 82', cx: 41, cy: 41, r: 36 };
  return (
    <div className={clsx('n8n-node', `type-${isAgent ? 'agent' : node.type || 'agent'}`, state)} style={{ left: node.x, top: node.y, '--nd-color': color, '--nd-bg': `${color}14`, '--nd-border': `${color}44` } as React.CSSProperties} role="img" aria-label={node.label}>
      <div className="exec-ring"><svg viewBox={ring.vb}><circle cx={ring.cx} cy={ring.cy} r={ring.r} className="exec-ring-arc" /></svg></div>
      <div className="nd-icon">{renderNodeIcon(node)}</div>
      {isAgent ? <div className="nd-agent-name">{node.label}</div> : null}
      <div className="nd-title">{node.label}{node.sub ? <span className="nd-subtitle">{node.sub}</span> : null}</div>
      <div className="nd-port port-left" />
      <div className="nd-port port-right" />
      <div className="nd-port port-bottom" />
      <div className="nd-done-mark">v</div>
      <div className="nd-err-mark">x</div>
    </div>
  );
}

function LogEntry({ event, showConnector }: { event: ExecutionEvent; showConnector: boolean }) {
  const [expanded, setExpanded] = useState(Boolean(event.error_message || event.output_summary));
  const status = event.status === 'failed' ? 'error' : event.status === 'running' ? 'active' : 'done';
  const entries = [['Description', event.description], ['Input', event.input_summary], ['Output', event.output_summary], ['Reasoning', event.reasoning_summary], ['Error', event.error_message], ['Tool', event.tool_name]].filter((entry): entry is [string, string] => Boolean(entry[1]));
  return (
    <>
      {showConnector ? <div className="log-connector" /> : null}
      <div className={clsx('log-entry', status, expanded && 'expanded', entries.length && 'has-details')}>
        <button className="log-entry-header" onClick={() => setExpanded((value) => !value)}>
          <div className="log-status-dot">{status === 'active' ? 'o' : status === 'error' ? 'x' : 'v'}</div>
          <div className="log-thought-label">{event.node_name ? `${event.node_name}: ` : ''}{event.title || event.event_type}<span className="log-ts-label">{event.created_at ? new Date(event.created_at).toLocaleTimeString('en-IN', { hour12: false }) : ''}</span></div>
          {entries.length ? <div className="log-chevron">›</div> : null}
        </button>
        {entries.length ? (
          <div className="log-thought-body"><div className="log-details-grid">{entries.map(([label, value]) => <div key={label} className={clsx('log-detail-item', (label === 'Input' || label === 'Output') && 'important')}><div className="log-detail-label">{label}</div><div className="log-detail-value">{value}</div></div>)}</div></div>
        ) : null}
      </div>
    </>
  );
}

function FallbackLogs({ issue, isSummary }: { issue: Issue; isSummary: boolean }) {
  const steps = issue.workflow_key === 'incident_daddy' ? ['Issues Tracker', 'Escalation Agent', 'Jira Agent', 'Incident Daddy'] : ['Issues Tracker', 'Escalation Agent', 'Jira Agent', 'Bug Daddy', 'SME Agent', 'Planner', 'Planner Critique', 'Context Analyser', 'Context Critique', 'Coder', 'Coder Critique', 'GitHub', 'Reviewer Daddy'];
  return (
    <>
      <div className="execution-note">{isSummary ? 'Execution summary preview' : 'Waiting for backend execution events. Local workflow animation is shown on the canvas.'}</div>
      {steps.map((step, index) => (
        <div key={step} className={clsx('log-step-group', index > 1 && !isSummary && 'collapsed')}>
          <div className="log-step-header"><span className="step-chevron">▾</span><span className="step-icon">{String(index + 1).padStart(2, '0')}</span><span className="step-name">{step}</span><span className={clsx('step-status n8n-step-chip', isSummary || index < 2 ? 'done' : 'running')}>{isSummary || index < 2 ? 'DONE' : 'READY'}</span></div>
          <div className="log-step-body"><div className="log-entry info"><strong>{step}</strong><p>{issue.jiraId} / {issue.shortSvc} / freq={issue.frequency}</p></div></div>
        </div>
      ))}
    </>
  );
}

export function ExecutionGraphModal({
  issue,
  isSummary,
  explicitSessionId,
  onClose,
  onComplete,
}: {
  issue: Issue;
  isSummary: boolean;
  explicitSessionId?: string;
  onClose: () => void;
  onComplete: (issueId: number) => void;
}) {
  const [zoom, setZoom] = useState(0.55);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const sessionId = explicitSessionId || issue.latest_execution_session_id || issue.execution_session_id || '';
  const workflowKey = issue.workflow_key || issue.agent_target || 'bug_daddy';
  const [nodeStates, setNodeStates] = useState<Record<string, string>>(() => initialGraphNodeStates(workflowKey, isSummary));
  const afterIdRef = useRef(0);
  const dragRef = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null);

  const graphQuery = useQuery({
    queryKey: ['workflow-graph', sessionId || workflowKey],
    queryFn: async () => {
      if (sessionId) {
        const data = await apiJson<{ workflow?: { graph_json?: WorkflowGraph }; graph_json?: WorkflowGraph; nodes?: WorkflowNode[]; edges?: WorkflowEdge[] }>(`/agent/executions/${sessionId}/graph`);
        return data.workflow?.graph_json || data.graph_json || (data as WorkflowGraph);
      }
      const data = await apiJson<{ workflow?: { graph_json?: WorkflowGraph }; graph_json?: WorkflowGraph; nodes?: WorkflowNode[]; edges?: WorkflowEdge[] }>(`/agent/workflows/${workflowKey}`);
      return data.workflow?.graph_json || data.graph_json || (data as WorkflowGraph);
    },
    retry: false,
  });

  const graph = useMemo(() => normalizeWorkflowGraph(graphQuery.data as WorkflowGraph | undefined), [graphQuery.data]);
  const edges = useMemo(() => graph.edges.map(normalizeEdge), [graph.edges]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const activePath = useMemo(() => activePathForWorkflow(workflowKey), [workflowKey]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) { if (event.key === 'Escape') onClose(); }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    afterIdRef.current = 0;
    if (sessionId || isSummary) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    activePath.forEach((nodeId, index) => {
      timers.push(setTimeout(() => setNodeStates((state) => ({ ...state, [nodeId]: 'active' })), 450 + index * 620));
      timers.push(setTimeout(() => setNodeStates((state) => ({ ...state, [nodeId]: 'done' })), 880 + index * 620));
    });
    return () => timers.forEach(clearTimeout);
  }, [activePath, isSummary, issue.id, sessionId]);

  useEffect(() => {
    if (!sessionId || isSummary) return;
    let stopped = false;
    async function poll() {
      try {
        const data = await apiJson<ListResponse<ExecutionEvent>>(`/agent/executions/${sessionId}/events?after_id=${afterIdRef.current}&limit=200`);
        if (stopped || !data.items.length) return;
        setEvents((items) => [...items, ...data.items]);
        afterIdRef.current = Math.max(afterIdRef.current, ...data.items.map((item) => item.id || 0));
        const nextStates: Record<string, string> = {};
        data.items.forEach((ev) => {
          if (!ev.node_id) return;
          const nodeId = canonicalNodeId(ev.node_id);
          if (ev.event_type.endsWith('.started') || ev.status === 'running') nextStates[nodeId] = 'active';
          if (ev.event_type.endsWith('.completed') || ev.status === 'succeeded') nextStates[nodeId] = 'done';
          if (ev.event_type.endsWith('.failed') || ev.status === 'failed') nextStates[nodeId] = 'error';
          if (ev.event_type === 'session.completed') onComplete(issue.id);
        });
        if (Object.keys(nextStates).length) setNodeStates((state) => ({ ...state, ...nextStates }));
      } catch { /* transient error */ }
    }
    void poll();
    const timer = setInterval(poll, 1500);
    return () => { stopped = true; clearInterval(timer); };
  }, [isSummary, issue.id, onComplete, sessionId]);

  const activeEdges = new Set(edges.filter(([from, to]) => nodeStates[from] || nodeStates[to]).map(([from, to]) => `${from}-${to}`));

  function handleWheel(event: React.WheelEvent<HTMLDivElement>) {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      setZoom((value) => Math.max(0.3, Math.min(2.5, value - event.deltaY * 0.005)));
      return;
    }
    setPan((value) => ({ x: value.x - event.deltaX, y: value.y - event.deltaY }));
  }

  function beginPan(event: React.MouseEvent<HTMLDivElement>) {
    if (event.target instanceof Element && event.target.closest('.n8n-node')) return;
    dragRef.current = { startX: event.clientX, startY: event.clientY, panX: pan.x, panY: pan.y };
  }

  function movePan(event: React.MouseEvent<HTMLDivElement>) {
    if (!dragRef.current) return;
    setPan({ x: dragRef.current.panX + event.clientX - dragRef.current.startX, y: dragRef.current.panY + event.clientY - dragRef.current.startY });
  }

  function endPan() { dragRef.current = null; }

  const progressSteps = workflowKey === 'incident_daddy'
    ? ['Analyze', 'Route', 'JIRA Update', 'Resolve']
    : ['Analyze', 'Plan', 'Code', 'Review', 'Deploy'];

  const doneNodes = Object.entries(nodeStates).filter(([, s]) => s === 'done').map(([id]) => id);
  const activeNode = Object.entries(nodeStates).find(([, s]) => s === 'active')?.[0];

  function getStepState(stepIdx: number) {
    const stepsTotal = progressSteps.length;
    const doneCount = doneNodes.filter((id) => activePath.indexOf(id) >= 0).length;
    const activeIdx = activeNode ? activePath.indexOf(activeNode) : -1;
    const fraction = activePath.length > 0 ? activePath.length / stepsTotal : 1;
    const stepThreshold = Math.round(stepIdx * fraction);
    if (doneCount > stepThreshold) return 'done';
    if (activeIdx >= 0 && Math.round(activeIdx / fraction) === stepIdx) return 'active';
    return '';
  }

  return (
    <div className="modal-ov" role="dialog" aria-modal="true" onMouseDown={(event: MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) onClose(); }}>
      <motion.div
        initial={{ opacity: 0, scale: 0.88, y: 24 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 16 }}
        transition={{ type: 'spring', damping: 22, stiffness: 280 }}
        className="modal"
      >
        <div className="modal-hdr">
          <div>
            <div className="modal-title"><GitBranch size={18} /> {isSummary ? 'Execution Summary' : 'Live Execution Graph'} <span>{issue.jiraId}</span></div>
            <div className="modal-sub">{issue.shortSvc} / freq={issue.freq} / {issue.criticality} / {sessionId || 'workflow preview'}</div>
          </div>
          <button className="modal-close" onClick={onClose}><X size={14} /> Close</button>
        </div>

        {/* Step progress strip */}
        <div className="modal-progress">
          {progressSteps.map((step, idx) => {
            const state = getStepState(idx);
            return (
              <React.Fragment key={step}>
                <div className={`mp-step ${state}`}>
                  <div className="mp-step-dot">{state === 'done' ? '✓' : idx + 1}</div>
                  {step}
                </div>
                {idx < progressSteps.length - 1 && (
                  <div className={`mp-sep ${getStepState(idx) === 'done' ? 'done' : ''}`} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        <div className="modal-body">
          <div className="n8n-canvas" onWheel={handleWheel} onMouseDown={beginPan} onMouseMove={movePan} onMouseUp={endPan} onMouseLeave={endPan}>
            <div className="n8n-canvas-inner" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
              <GroupBox label="Incident Route" x={40} y={330} w={210} h={170} color="var(--c2)" />
              <GroupBox label="Knowledge Base" x={285} y={340} w={190} h={145} color="var(--c4)" />
              <GroupBox label="Remediation Pipeline" x={510} y={280} w={700} h={390} color="var(--c1)" />
              <GroupBox label="Review Pipeline" x={1220} y={280} w={210} h={160} color="var(--c5)" />
              <svg className="n8n-edges" viewBox="0 0 1500 900" preserveAspectRatio="none">
                {edges.map(([from, to]) => {
                  const source = nodeById.get(from);
                  const target = nodeById.get(to);
                  if (!source || !target) return null;
                  const path = edgePath(source, target, edges);
                  const active = activeEdges.has(`${from}-${to}`);
                  return (
                    <g key={`${from}-${to}`} className={clsx('edge-group', active && 'active')}>
                      <path d={path} style={{ stroke: nodeColor(source) }} />
                      {active ? <circle r="3" fill={nodeColor(target)}><animateMotion dur="2s" repeatCount="indefinite" path={path} /></circle> : null}
                    </g>
                  );
                })}
              </svg>
              {graph.nodes.map((node) => <GraphNode key={node.id} node={node} state={nodeStates[node.id]} />)}
            </div>
            <div className="n8n-zoom">
              <button onClick={() => setZoom((z) => Math.min(2.5, z + 0.1))}>+</button>
              <div className="n8n-zoom-level">{Math.round(zoom * 100)}%</div>
              <button onClick={() => setZoom((z) => Math.max(0.3, z - 0.1))}>-</button>
              <button onClick={() => { setZoom(0.55); setPan({ x: 0, y: 0 }); }}>Reset</button>
            </div>
          </div>
          <div className="n8n-right">
            <div className="n8n-log-stream">
              {events.length ? events.map((event, index) => <LogEntry key={event.id} event={event} showConnector={index > 0} />) : <FallbackLogs issue={issue} isSummary={isSummary} />}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
