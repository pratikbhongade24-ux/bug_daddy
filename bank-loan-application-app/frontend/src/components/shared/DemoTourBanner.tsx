'use client';

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, X } from 'lucide-react';

export function DemoTourBanner({ onDismiss }: { onDismiss?: () => void }) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onDismiss?.();
    }, 12000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8, height: 0 }}
          transition={{ duration: 0.4, ease: [0.2, 0.8, 0.2, 1] }}
          className="demo-banner"
        >
          <div className="demo-banner-icon">
            <Sparkles size={14} />
          </div>
          <span>
            <strong>AI Demo Mode Active</strong> — Click any issue from the{' '}
            <strong>Escalation Queue</strong> to watch AI agents analyze, plan, and fix in real-time.
            Press <kbd style={{ fontFamily: 'var(--mono)', background: 'rgba(139,92,246,0.1)', padding: '1px 5px', borderRadius: 4, border: '1px solid rgba(139,92,246,0.2)' }}>⌘K</kbd> for quick actions.
          </span>
          <button
            className="demo-banner-close"
            onClick={() => { setVisible(false); onDismiss?.(); }}
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
