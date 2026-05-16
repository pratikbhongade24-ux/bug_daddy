import React, { FormEvent, useMemo, useState } from 'react';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { Power, RefreshCcw, Shield, SlidersHorizontal } from 'lucide-react';
import { AiQueueStatus, User, ToastKind } from '@/lib/types';
import { apiJson, errorMessage } from '@/lib/api';
import { PanelHeader } from '../shared/PanelHeader';
import { motion } from 'framer-motion';
import { AsyncActionButton } from '../shared/AsyncActionButton';

function queueStatusClass(status: string | null | undefined) {
  const s = (status || '').toLowerCase();
  if (s === 'processing' || s === 'in_progress' || s === 'running') return 'qstat-processing';
  if (s === 'queued' || s === 'pending') return 'qstat-queued';
  if (s === 'completed' || s === 'done' || s === 'resolved') return 'qstat-completed';
  if (s === 'failed' || s === 'error') return 'qstat-failed';
  return 'qstat-default';
}

export function AdminView({
  users,
  aiQueue,
  loading,
  queueLoading,
  loadError,
  toast,
  refresh,
}: {
  users: User[];
  aiQueue?: AiQueueStatus;
  loading: boolean;
  queueLoading: boolean;
  loadError?: string;
  toast: (message: string, kind?: ToastKind) => void;
  refresh: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' });
  const [queueLength, setQueueLength] = useState('');
  const [queueSearch, setQueueSearch] = useState('');
  const [queueStatusFilter, setQueueStatusFilter] = useState('');
  const [queueSort, setQueueSort] = useState<'updated_desc' | 'updated_asc' | 'attempts_desc'>('updated_desc');
  const [userSearch, setUserSearch] = useState('');
  const [userRoleFilter, setUserRoleFilter] = useState('');
  const [userStatusFilter, setUserStatusFilter] = useState('');
  
  const createMutation = useMutation({
    mutationFn: () => apiJson<User>('/admin/users', { method: 'POST', body: JSON.stringify({ ...form, full_name: form.full_name || null }) }),
    onSuccess: async (user) => {
      toast(`Created user ${user.username}`, 'ok');
      setForm({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' });
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (error) => toast(errorMessage(error, 'Could not create user'), 'err'),
  });
  const queueConfig = aiQueue?.config;
  const displayQueueLength = queueLength || String(queueConfig?.queue_length ?? 3);
  const queueItems = aiQueue?.items || [];
  const queueStatuses = Array.from(new Set(queueItems.map((i) => i.status).filter(Boolean))).sort();

  const filteredQueueItems = useMemo(() => {
    const q = queueSearch.trim().toLowerCase();
    const rows = queueItems
      .filter((item) => !queueStatusFilter || item.status === queueStatusFilter)
      .filter((item) => {
        if (!q) return true;
        return (
          String(item.issue_id).includes(q) ||
          (item.service_name || '').toLowerCase().includes(q) ||
          (item.worker_id || '').toLowerCase().includes(q) ||
          (item.status || '').toLowerCase().includes(q)
        );
      });
    if (queueSort === 'attempts_desc') {
      return [...rows].sort((a, b) => b.attempts - a.attempts);
    }
    if (queueSort === 'updated_asc') {
      return [...rows].sort((a, b) => (a.updated_at || '').localeCompare(b.updated_at || ''));
    }
    return [...rows].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  }, [queueItems, queueSearch, queueStatusFilter, queueSort]);

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    return users
      .filter((user) => !userRoleFilter || user.role === userRoleFilter)
      .filter((user) => !userStatusFilter || user.status === userStatusFilter)
      .filter((user) => {
        if (!q) return true;
        return (
          user.username.toLowerCase().includes(q) ||
          user.email.toLowerCase().includes(q) ||
          (user.full_name || '').toLowerCase().includes(q)
        );
      })
      .sort((a, b) => a.username.localeCompare(b.username));
  }, [users, userSearch, userRoleFilter, userStatusFilter]);

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

  async function toggleUser(user: User) {
    try {
      const data = await apiJson<User>('/admin/users/' + user.id, {
        method: 'PATCH',
        body: JSON.stringify({ status: user.status === 'active' ? 'inactive' : 'active' }),
      });
      toast(`User ${data.username} is now ${data.status}`, 'ok');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    } catch (error) {
      toast(errorMessage(error, 'Status update failed'), 'err');
    }
  }

  async function resetPassword(user: User) {
    const newPassword = window.prompt('Enter a new password for ' + user.username);
    if (!newPassword) return;
    try {
      await apiJson('/admin/users/' + user.id + '/password', {
        method: 'PATCH',
        body: JSON.stringify({ new_password: newPassword }),
      });
      toast('Password updated for ' + user.username, 'ok');
    } catch (error) {
      toast(errorMessage(error, 'Password reset failed'), 'err');
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="view active">
      <PanelHeader
        title="Admin Console"
        subtitle="User provisioning and access controls"
        icon={<Shield size={18} />}
        actions={
          <button className="btn" onClick={refresh}>
            <RefreshCcw size={14} /> Refresh Users
          </button>
        }
      />
      {loadError ? <div className="section-alert" role="alert">{loadError}</div> : null}
      <div className="admin-grid">
        <div className="admin-stack">
          <section className="admin-card admin-form">
            <div className="admin-card-head">AI Queue</div>
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
              <span>{queueLoading ? 'Loading...' : 'SQS automation'}</span>
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
          <form
            className="admin-card admin-form"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              createMutation.mutate();
            }}
          >
            <div className="admin-card-head">Create User</div>
            <label>
              Username
              <input required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
            </label>
            <label>
              Email
              <input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
            </label>
            <label>
              Full Name
              <input value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
            </label>
            <label>
              Password
              <input required type="password" minLength={8} value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
            </label>
            <label>
              Role
              <select value={form.role_name} onChange={(event) => setForm({ ...form, role_name: event.target.value })}>
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <label>
              Status
              <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="locked">Locked</option>
              </select>
            </label>
            <div className="admin-actions">
              <AsyncActionButton className="btn pri" type="submit" pending={createMutation.isPending} pendingLabel="Creating...">
                Create User
              </AsyncActionButton>
              <button
                className="btn"
                type="button"
                onClick={() => setForm({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' })}
              >
                Clear
              </button>
            </div>
          </form>
        </div>
        <section className="admin-card admin-list-card">
          <div className="admin-card-head">AI Queue Activity</div>
          <div className="admin-table-toolbar">
            <input
              className="admin-table-search"
              placeholder="Search issue/service/worker..."
              value={queueSearch}
              onChange={(event) => setQueueSearch(event.target.value)}
            />
            <select className="admin-table-select" value={queueStatusFilter} onChange={(event) => setQueueStatusFilter(event.target.value)}>
              <option value="">All status</option>
              {queueStatuses.map((status) => (
                <option key={status} value={status}>{status}</option>
              ))}
            </select>
            <select className="admin-table-select" value={queueSort} onChange={(event) => setQueueSort(event.target.value as typeof queueSort)}>
              <option value="updated_desc">Latest first</option>
              <option value="updated_asc">Oldest first</option>
              <option value="attempts_desc">Highest attempts</option>
            </select>
          </div>
          <div className="admin-list-wrap queue-activity-wrap">
            <table className="admin-table">
              <colgroup>
                <col className="aq-col-issue" />
                <col className="aq-col-service" />
                <col className="aq-col-status" />
                <col className="aq-col-worker" />
                <col className="aq-col-attempts" />
                <col className="aq-col-updated" />
              </colgroup>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Service</th>
                  <th>Status</th>
                  <th>Worker</th>
                  <th>Attempts</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {filteredQueueItems.map((item) => (
                  <tr key={item.id}>
                    <td className="td-id">#{item.issue_id}</td>
                    <td className="td-own">{item.service_name || '-'}</td>
                    <td><span className={`admin-badge qstat ${queueStatusClass(item.status)}`}>{item.status}</span></td>
                    <td className="td-desc" title={item.worker_id || ''}>{item.worker_id || '-'}</td>
                    <td className="td-own"><span className="attempt-pill">{item.attempts}</span></td>
                    <td>{item.updated_at ? new Date(item.updated_at).toLocaleString('en-IN') : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {queueLoading ? <div className="empty-state">Loading queue...</div> : null}
            {!queueLoading && !filteredQueueItems.length ? <div className="empty-state">No queue activity matches these filters.</div> : null}
          </div>
          <div className="admin-card-head admin-card-head-spaced">Users</div>
          <div className="admin-table-toolbar">
            <input
              className="admin-table-search"
              placeholder="Search username/email/name..."
              value={userSearch}
              onChange={(event) => setUserSearch(event.target.value)}
            />
            <select className="admin-table-select" value={userRoleFilter} onChange={(event) => setUserRoleFilter(event.target.value)}>
              <option value="">All roles</option>
              <option value="admin">admin</option>
              <option value="user">user</option>
            </select>
            <select className="admin-table-select" value={userStatusFilter} onChange={(event) => setUserStatusFilter(event.target.value)}>
              <option value="">All status</option>
              <option value="active">active</option>
              <option value="inactive">inactive</option>
              <option value="locked">locked</option>
            </select>
          </div>
          <div className="admin-list-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last Login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((user) => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>
                      <span className="admin-badge">{user.role}</span>
                    </td>
                    <td>
                      <span className="badge med">{user.status}</span>
                    </td>
                    <td>{user.last_login_at ? new Date(user.last_login_at).toLocaleString('en-IN') : 'Never'}</td>
                    <td>
                      <button className="act-btn sum-btn" onClick={() => resetPassword(user)}>
                        Reset Password
                      </button>
                      <button className="act-btn pri-btn" onClick={() => toggleUser(user)}>
                        {user.status === 'active' ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading ? <div className="empty-state">Loading users...</div> : null}
            {!loading && !filteredUsers.length ? <div className="empty-state">No users match these filters.</div> : null}
          </div>
        </section>
      </div>
    </motion.div>
  );
}
