'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import clsx from 'clsx';
import { apiBase } from '@/lib/api';

export function ResetPage() {
  const router = useRouter();
  const params = useSearchParams();
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [kind, setKind] = useState<'ok' | 'err' | ''>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setToken(params.get('token') || '');
  }, [params]);

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    setMessage('');
    setKind('');
    try {
      setLoading(true);
      const response = await fetch(apiBase() + '/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token.trim(), new_password: password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setMessage(data.detail || 'Password reset failed.');
        setKind('err');
        return;
      }
      setMessage('Password updated successfully. Redirecting to login...');
      setKind('ok');
      setTimeout(() => {
        router.push('/login');
      }, 1200);
    } catch {
      setMessage('Unable to reach the reset API.');
      setKind('err');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-screen">
      <section className="reset-card" aria-label="Reset password">
        <div className="reset-title">Reset Password</div>
        <p className="reset-sub">Use the reset token generated from the login page. This updates the account password through the live auth API.</p>
        {message ? <div className={clsx('reset-msg', kind)}>{message}</div> : null}
        <form onSubmit={submitReset}>
          <div className="form-group">
            <label className="form-label" htmlFor="token">
              Reset Token
            </label>
            <input id="token" className="reset-input" placeholder="paste reset token" required value={token} onChange={(event) => setToken(event.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="new-password">
              New Password
            </label>
            <input
              id="new-password"
              className="reset-input"
              type="password"
              placeholder="minimum 8 characters"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? 'Updating...' : 'Update Password'}
          </button>
        </form>
        <div className="reset-foot">
          <a href="/login">Back to login</a>
        </div>
      </section>
    </main>
  );
}
