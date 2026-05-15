'use client';

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain } from 'lucide-react';

const AGENT_MESSAGES = [
  'Analyzing error context…',
  'Running Planner agent…',
  'Generating fix strategy…',
  'Critiquing solution…',
  'Writing code patch…',
  'Reviewing PR…',
  'Updating JIRA ticket…',
];

export function AiThinkingBadge({
  isActive,
  agentName,
  issueName,
}: {
  isActive: boolean;
  agentName?: string;
  issueName?: string;
}) {
  const [msgIndex, setMsgIndex] = useState(0);
  const [displayed, setDisplayed] = useState('');
  const fullMsg = agentName && issueName
    ? `${agentName} → ${issueName}`
    : AGENT_MESSAGES[msgIndex];

  // Typewriter effect
  useEffect(() => {
    if (!isActive) return;
    setDisplayed('');
    let i = 0;
    const timer = setInterval(() => {
      i++;
      setDisplayed(fullMsg.slice(0, i));
      if (i >= fullMsg.length) clearInterval(timer);
    }, 28);
    return () => clearInterval(timer);
  }, [isActive, fullMsg, msgIndex]);

  // Cycle through messages
  useEffect(() => {
    if (!isActive || (agentName && issueName)) return;
    const timer = setInterval(() => {
      setMsgIndex((i) => (i + 1) % AGENT_MESSAGES.length);
    }, 3200);
    return () => clearInterval(timer);
  }, [isActive, agentName, issueName]);

  return (
    <AnimatePresence>
      {isActive && (
        <motion.div
          initial={{ opacity: 0, x: -20, y: 10 }}
          animate={{ opacity: 1, x: 0, y: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ type: 'spring', damping: 22, stiffness: 280 }}
          className="ai-thinking-badge"
        >
          <div className="ai-thinking-icon">
            <Brain size={18} />
          </div>
          <div className="ai-thinking-text">
            <div className="ai-thinking-label">AI Agents Active</div>
            <div className="ai-thinking-msg">
              {displayed}
              {displayed.length < fullMsg.length ? (
                <span style={{ borderRight: '2px solid var(--c5)', animation: 'typeCaret 0.7s step-end infinite' }}>&nbsp;</span>
              ) : null}
            </div>
          </div>
          <div className="ai-thinking-dots">
            <span /><span /><span />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
