import clsx from 'clsx';
import { ToastItem } from '@/lib/types';

export function ToastContainer({ toasts }: { toasts: ToastItem[] }) {
  return (
    <div className="toastc" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className={clsx('toast', toast.kind)} role={toast.kind === 'err' ? 'alert' : 'status'}>
          <span aria-hidden="true">{toast.kind === 'ok' ? '✓' : toast.kind === 'err' ? '!' : 'i'}</span>
          {toast.message}
        </div>
      ))}
    </div>
  );
}
