'use client';

import { FormEvent, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { KeyRound, UserRound } from 'lucide-react';
import { apiBase } from '@/lib/api';
import { ACCESS_TOKEN_KEY, USER_KEY, storeSession } from '@/lib/storage';
import type { AuthResponse } from '@/lib/types';

export function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(USER_KEY) && localStorage.getItem(ACCESS_TOKEN_KEY)) {
      router.replace('/dashboard');
    }
  }, [router]);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!identifier.trim() || !password) {
      setError('Enter both username/email and password.');
      return;
    }
    try {
      setLoading(true);
      const response = await fetch(apiBase() + '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: identifier.trim(), password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || 'Login failed.');
        return;
      }
      const auth = data as AuthResponse;
      storeSession(auth.access_token, auth.refresh_token, auth.user);
      router.push('/dashboard');
    } catch {
      setError('Unable to reach the login API.');
    } finally {
      setLoading(false);
    }
  }

  async function handleForgotPassword(event: React.MouseEvent) {
    event.preventDefault();
    setError('');
    if (!identifier.trim()) {
      setError('Enter a username or email first.');
      return;
    }
    try {
      const response = await fetch(apiBase() + '/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier: identifier.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || 'Could not generate reset token.');
        return;
      }
      setError('Reset token created. Opening reset page...');
      setTimeout(() => {
        router.push('/reset?token=' + encodeURIComponent(data.reset_token));
      }, 600);
    } catch {
      setError('Unable to reach the password reset API.');
    }
  }

  return (
    <main className="auth-screen">
      <section className="login-card" aria-label="Sign in">
        <div className="auth-header">
          <div className="auth-title">
            <span className="title-icon">AI</span>
            BUG DADDY <span className="title-skull">X</span> <span className="v2">2.0</span>
          </div>
          <div className="auth-subtitle">Sign In</div>
        </div>

        {error ? <div className="error-msg show">{error}</div> : null}

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label className="form-label" htmlFor="identifier">
              Username or Email
            </label>
            <div className="input-wrap">
              <UserRound className="input-icon-svg" size={17} />
              <input
                id="identifier"
                className="form-input"
                placeholder="bug_daddy or name@domain.com"
                required
                value={identifier}
                onChange={(event) => setIdentifier(event.target.value)}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">
              Password
            </label>
            <div className="input-wrap">
              <KeyRound className="input-icon-svg" size={17} />
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="minimum 8 characters"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
          </div>

          <div className="forgot-pwd">
            <a href="#" onClick={handleForgotPassword}>
              Forgot Password?
            </a>
          </div>

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Signing In...' : 'Sign In'}
          </button>
        </form>

        <div className="divider">or continue with</div>

        <button className="btn-sso" type="button" onClick={() => setError('Microsoft SSO is not wired yet. Use the API-backed credentials.')}>
          <span className="ms-grid" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </span>
          Sign in with Microsoft
          <span className="tooltip">Tip: Use your Azure Active Directory credentials to single-sign on.</span>
        </button>
      </section>
    </main>
  );
}
