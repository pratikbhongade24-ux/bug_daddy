'use client';

import React, { useRef, useState } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';

export function SpotlightCard({
  children,
  className,
  spotlightColor = 'rgba(59, 130, 246, 0.1)',
  onClick,
  style,
}: {
  children: React.ReactNode;
  className?: string;
  spotlightColor?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  const divRef = useRef<HTMLDivElement>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!divRef.current || isFocused) return;

    const div = divRef.current;
    const rect = div.getBoundingClientRect();

    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const handleFocus = () => {
    setIsFocused(true);
    setOpacity(1);
  };

  const handleBlur = () => {
    setIsFocused(false);
    setOpacity(0);
  };

  const handleMouseEnter = () => {
    setOpacity(1);
  };

  const handleMouseLeave = () => {
    setOpacity(0);
  };

  return (
    <motion.div
      ref={divRef}
      onMouseMove={handleMouseMove}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={onClick}
      className={clsx('spotlight-card', className)}
      style={{
        ...style,
        position: 'relative',
        overflow: 'hidden',
        borderRadius: 'var(--radius)',
        border: '1px solid var(--bd)',
        background: 'var(--s2)',
        boxShadow: 'var(--shadow-sm)',
        transition: 'all 0.3s var(--ease-apple)',
        cursor: onClick ? 'pointer' : 'default',
      }}
      whileHover={{ y: -2, boxShadow: 'var(--shadow-md)' }}
      whileTap={{ scale: onClick ? 0.98 : 1 }}
    >
      <div
        style={{
          position: 'absolute',
          top: -1,
          left: -1,
          right: -1,
          bottom: -1,
          pointerEvents: 'none',
          opacity,
          transition: 'opacity 0.3s var(--ease-apple)',
          background: `radial-gradient(600px circle at ${position.x}px ${position.y}px, ${spotlightColor}, transparent 40%)`,
        }}
      />
      <div style={{ position: 'relative', height: '100%', width: '100%' }}>{children}</div>
    </motion.div>
  );
}
