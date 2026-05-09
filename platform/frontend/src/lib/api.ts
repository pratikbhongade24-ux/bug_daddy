import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, clearSession, storeSession } from './storage';
import type { AuthResponse } from './types';

export function apiBase() {
  if (typeof window === 'undefined') return '';
  return window.location.hostname === 'localhost' ? 'http://localhost:8000' : window.location.origin + '/api';
}

let refreshPromise: Promise<boolean> | null = null;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `API request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function refreshAccessToken() {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;
  const response = await fetch(apiBase() + '/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  const data = (await response.json()) as AuthResponse;
  storeSession(data.access_token, data.refresh_token, data.user);
  return true;
}

function redirectToLogin() {
  clearSession();
  if (typeof window !== 'undefined') window.location.href = '/login';
}

export async function apiFetch(path: string, options: RequestInit = {}, retry = true): Promise<Response> {
  const accessToken = typeof window !== 'undefined' ? localStorage.getItem(ACCESS_TOKEN_KEY) : null;
  const headers = new Headers(options.headers);
  if (!headers.has('Content-Type') && options.body) headers.set('Content-Type', 'application/json');
  if (accessToken) headers.set('Authorization', 'Bearer ' + accessToken);

  const response = await fetch(apiBase() + path, { ...options, headers });
  if (response.status !== 401 || !retry) return response;

  refreshPromise ??= refreshAccessToken().finally(() => {
    refreshPromise = null;
  });
  const refreshed = await refreshPromise;
  if (!refreshed) {
    redirectToLogin();
    throw new ApiError(401, 'Unauthorized');
  }
  return apiFetch(path, options, false);
}

export async function apiJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, options);
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, data?.detail ?? data ?? response.statusText);
  return data as T;
}

export async function logoutRequest() {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  try {
    if (refreshToken && accessToken) {
      await fetch(apiBase() + '/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + accessToken },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    }
  } finally {
    redirectToLogin();
  }
}

export function errorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) return String(error.detail || fallback);
  if (error instanceof Error) return error.message;
  return fallback;
}
