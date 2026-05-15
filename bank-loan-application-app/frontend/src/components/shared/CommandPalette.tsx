'use client';

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, LayoutDashboard, Bug, ShieldCheck, Zap, Activity, Brain, AlertTriangle } from 'lucide-react';
import { ViewName, Issue } from '@/lib/types';

type AiSuggestion = {
  id: string;
  label: string;
  action: () => void;
};

export function CommandPalette({
  isOpen,
  setIsOpen,
  setView,
  onEscalate,
  issues,
}: {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  setView: (view: ViewName) => void;
  onEscalate: () => void;
  issues?: Issue[];
}) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, setIsOpen]);

  if (!isOpen) return null;

  const actions = [
    { id: 'dashboard', label: 'Go to Dashboard', icon: <LayoutDashboard size={14} />, action: () => setView('dashboard') },
    { id: 'issues', label: 'Go to Issues Workbench', icon: <Bug size={14} />, action: () => setView('issues') },
    { id: 'sonar', label: 'Go to SonarQube', icon: <ShieldCheck size={14} />, action: () => setView('sonar') },
    { id: 'escalate', label: 'Escalate All Critical Issues', icon: <Zap size={14} />, action: onEscalate },
    { id: 'activity', label: 'View Live Agent Feed', icon: <Activity size={14} />, action: () => setView('dashboard') },
  ];

  // AI-powered context suggestions derived from live data
  const aiSuggestions: AiSuggestion[] = [];
  const criticals = issues?.filter((i) => i.criticality === 'Critical' && i.tab !== 'resolved') ?? [];
  const wip = issues?.filter((i) => i.tab === 'wip') ?? [];

  if (criticals.length > 0) {
    aiSuggestions.push({
      id: 'ai-critical',
      label: `${criticals.length} critical issues need immediate attention`,
      action: () => { setView('issues'); setIsOpen(false); },
    });
  }
  if (wip.length > 3) {
    aiSuggestions.push({
      id: 'ai-wip',
      label: `${wip.length} issues in WIP — agents are actively resolving`,
      action: () => { setView('issues'); setIsOpen(false); },
    });
  }
  if (criticals.length === 0 && wip.length === 0) {
    aiSuggestions.push({
      id: 'ai-idle',
      label: 'All agents idle — run a Sonar scan to detect new issues',
      action: () => { setView('sonar'); setIsOpen(false); },
    });
  }

  const filtered = actions.filter((a) => a.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          zIndex: 500, display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
          paddingTop: '14vh',
          background: 'rgba(248, 250, 252, 0.5)',
          backdropFilter: 'blur(14px)',
        }}
        onClick={() => setIsOpen(false)}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: -12 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94, y: -12 }}
          transition={{ type: 'spring', damping: 26, stiffness: 320 }}
          style={{
            width: '100%', maxWidth: '620px', overflow: 'hidden',
            borderRadius: 'var(--radius)',
            border: '1px solid var(--bd)',
            background: 'rgba(255,255,255,0.96)',
            boxShadow: '0 32px 64px rgba(0,0,0,0.12), 0 0 0 1px rgba(0,0,0,0.04)',
            backdropFilter: 'blur(12px)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Search input */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid var(--bd)', padding: '14px 16px' }}>
            <Search size={16} style={{ color: 'var(--t3)', flexShrink: 0 }} />
            <input
              autoFocus
              style={{ flex: 1, background: 'transparent', color: 'var(--t)', outline: 'none', border: 'none', fontSize: '1rem' }}
              placeholder="Search commands or navigate..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <span style={{ borderRadius: 4, border: '1px solid var(--bd)', background: 'var(--s3)', padding: '2px 6px', fontSize: 11, fontWeight: 600, color: 'var(--t2)', fontFamily: 'var(--mono)' }}>ESC</span>
          </div>

          {/* Commands */}
          <div style={{ maxHeight: 280, overflowY: 'auto', padding: 8 }}>
            {filtered.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', fontSize: 14, color: 'var(--t2)' }}>No results found.</div>
            ) : (
              filtered.map((action) => (
                <button
                  key={action.id}
                  style={{
                    display: 'flex', width: '100%', alignItems: 'center', gap: 12,
                    borderRadius: 8, padding: '10px 12px', textAlign: 'left', fontSize: 14,
                    fontWeight: 500, color: 'var(--t2)', background: 'transparent', border: 'none',
                    cursor: 'pointer', transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--s3)'; e.currentTarget.style.color = 'var(--t)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--t2)'; }}
                  onClick={() => { action.action(); setIsOpen(false); setQuery(''); }}
                >
                  <span style={{ display: 'flex', width: 26, height: 26, alignItems: 'center', justifyContent: 'center', borderRadius: 6, background: 'var(--s3)', color: 'var(--c3)', flexShrink: 0 }}>
                    {action.icon}
                  </span>
                  {action.label}
                </button>
              ))
            )}
          </div>

          {/* AI Suggestions section — Intelligence layer */}
          {aiSuggestions.length > 0 && (
            <div className="cp-ai-section">
              <div className="cp-ai-label">
                <Brain size={10} style={{ color: 'var(--c5)' }} /> AI Insights
              </div>
              {aiSuggestions.map((s) => (
                <button
                  key={s.id}
                  className="cp-ai-suggestion"
                  onClick={() => { s.action(); setQuery(''); }}
                >
                  <span className="cp-ai-suggestion-icon">
                    <AlertTriangle size={11} />
                  </span>
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
