import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Bot, Power, RefreshCcw, SlidersHorizontal } from 'lucide-react';
import { motion } from 'framer-motion';
import { AiQueueStatus, ToastKind } from '@/lib/types';
import { apiJson, errorMessage } from '@/lib/api';
import { PanelHeader } from '../shared/PanelHeader';
import { AsyncActionButton } from '../shared/AsyncActionButton';

export function AiQueueView({
  aiQueue,
  loading,
  loadError,
  toast,
  refresh,
}: {
  aiQueue?: AiQueueStatus;
  loading: boolean;
  loadError?: string;
  toast: (message: string, kind?: ToastKind) => void;
  refresh: () => void;
}) {
  const queryClient = useQueryClient();
  const [queueLength, setQueueLength] = useState('');
  const queueConfig = aiQueue?.config;
  const displayQueueLength = queueLength || String(queueConfig?.queue_length ?? 3);

  const updateQueueMutation = useMutation({
    mutationFn: (payload: { is_active?: boolean; queue_length?: number }) => apiJson('/admin/ai-queue', { method: 'PATCH', body: JSON.stringify(payload) }),
    onSuccess: async () => {
      toast('AI queue settings updated', 'ok');
      setQueueLength('');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'ai-queue'] });
    },
    onError: (error) => toast(errorMessage(error, 'Could not update AI queue'), 'err'),
  });

  const replenishMutation = useMutation({
    mutationFn: () => apiJson('/admin/ai-queue/replenish', { method: 'POST' }),
    onSuccess: async () => {
      toast('AI queue replenished', 'ok');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'ai-queue'] });
    },
    onError: (error) => toast(errorMessage(error, 'Could not replenish AI queue'), 'err'),
  });

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="view active">
      <PanelHeader
        title="AI Queue"
        subtitle="Automated backlog dispatch and worker controls"
        icon={<Bot size={18} />}
        actions={
          <button className="btn" onClick={refresh}>
            <RefreshCcw size={14} /> Refresh
          </button>
        }
      />
      {loadError ? <div className="section-alert" role="alert">{loadError}</div> : null}
      <div className="admin-grid">
        <section className="admin-card admin-form">
          <div className="admin-card-head">Queue Controls</div>
          <div className="queue-kpis">
            <div><span>Active</span><strong>{aiQueue?.counts.active ?? 0}</strong></div>
            <div><span>Queued</span><strong>{aiQueue?.counts.queued ?? 0}</strong></div>
            <div><span>Processing</span><strong>{aiQueue?.counts.processing ?? 0}</strong></div>
            <div><span>Workers</span><strong>{aiQueue?.workers ?? 3}</strong></div>
          </div>
          <label>
            Queue Length
            <input
              type="number"
              min={1}
              max={50}
              value={displayQueueLength}
              onChange={(event) => setQueueLength(event.target.value)}
            />
          </label>
          <div className="queue-status-row">
            <span className={queueConfig?.is_active ? 'badge low' : 'badge med'}>
              {queueConfig?.is_active ? 'Active' : 'Inactive'}
            </span>
            <span>{loading ? 'Loading...' : 'SQS automation'}</span>
          </div>
          <div className="admin-actions">
            <AsyncActionButton
              className="btn pri"
              type="button"
              pending={updateQueueMutation.isPending}
              pendingLabel="Saving..."
              onClick={() => updateQueueMutation.mutate({ queue_length: Number(displayQueueLength) })}
            >
              <SlidersHorizontal size={14} /> Save
            </AsyncActionButton>
            <AsyncActionButton
              className="btn"
              type="button"
              pending={updateQueueMutation.isPending}
              pendingLabel="Updating..."
              onClick={() => updateQueueMutation.mutate({ is_active: !queueConfig?.is_active })}
            >
              <Power size={14} /> {queueConfig?.is_active ? 'Disable' : 'Enable'}
            </AsyncActionButton>
            <AsyncActionButton
              className="btn"
              type="button"
              pending={replenishMutation.isPending}
              pendingLabel="Refilling..."
              onClick={() => replenishMutation.mutate()}
            >
              <RefreshCcw size={14} /> Refill
            </AsyncActionButton>
          </div>
        </section>
        <section className="admin-card admin-list-card">
          <div className="admin-card-head">Queue Activity</div>
          <div className="admin-list-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Service</th>
                  <th>Status</th>
                  <th>Issue Status</th>
                  <th>Worker</th>
                  <th>Attempts</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {(aiQueue?.items || []).map((item) => (
                  <tr key={item.id}>
                    <td>{item.issue_id}</td>
                    <td>{item.service_name || '-'}</td>
                    <td><span className="admin-badge">{item.status}</span></td>
                    <td>{item.issue_status || '-'}</td>
                    <td>{item.worker_id || '-'}</td>
                    <td>{item.attempts}</td>
                    <td>{item.updated_at ? new Date(item.updated_at).toLocaleString('en-IN') : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading ? <div className="empty-state">Loading queue...</div> : null}
            {!loading && !(aiQueue?.items || []).length ? <div className="empty-state">No queue activity yet.</div> : null}
          </div>
        </section>
      </div>
    </motion.div>
  );
}
