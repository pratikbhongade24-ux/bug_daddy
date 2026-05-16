import React, { FormEvent, useState } from 'react';
import { useQueryClient, useMutation } from '@tanstack/react-query';
import { Shield, RefreshCcw } from 'lucide-react';
import { User, ToastKind } from '@/lib/types';
import { apiJson, errorMessage } from '@/lib/api';
import { PanelHeader } from '../shared/PanelHeader';
import { motion } from 'framer-motion';
import { AsyncActionButton } from '../shared/AsyncActionButton';

export function AdminView({
  users,
  loading,
  loadError,
  toast,
  refresh,
}: {
  users: User[];
  loading: boolean;
  loadError?: string;
  toast: (message: string, kind?: ToastKind) => void;
  refresh: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' });
  
  const createMutation = useMutation({
    mutationFn: () => apiJson<User>('/admin/users', { method: 'POST', body: JSON.stringify({ ...form, full_name: form.full_name || null }) }),
    onSuccess: async (user) => {
      toast(`Created user ${user.username}`, 'ok');
      setForm({ username: '', email: '', full_name: '', password: '', role_name: 'user', status: 'active' });
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (error) => toast(errorMessage(error, 'Could not create user'), 'err'),
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
        <section className="admin-card admin-list-card">
          <div className="admin-card-head">Users</div>
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
                {users.map((user) => (
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
            {!loading && !users.length ? <div className="empty-state">No users found.</div> : null}
          </div>
        </section>
      </div>
    </motion.div>
  );
}
