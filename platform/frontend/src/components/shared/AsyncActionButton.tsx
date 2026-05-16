'use client';

import React from 'react';
import clsx from 'clsx';
import { Loader2 } from 'lucide-react';

export function AsyncActionButton({
  className,
  pending,
  children,
  pendingLabel = 'Working...',
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  pending?: boolean;
  pendingLabel?: string;
}) {
  return (
    <button
      {...rest}
      disabled={pending || rest.disabled}
      className={clsx(className, pending && 'is-pending')}
      aria-busy={pending}
    >
      {pending ? (
        <span className="async-btn-inner">
          <Loader2 size={13} className="spin" />
          {pendingLabel}
        </span>
      ) : (
        children
      )}
    </button>
  );
}
