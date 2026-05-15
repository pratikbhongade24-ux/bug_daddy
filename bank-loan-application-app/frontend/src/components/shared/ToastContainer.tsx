import clsx from 'clsx';
import { ToastItem } from '@/lib/types';

export function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="toastc" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={clsx('toast', toast.kind)}>
          <span>{toast.kind === 'ok' ? 'v' : toast.kind === 'err' ? 'x' : 'i'}</span>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
