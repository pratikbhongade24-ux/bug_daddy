import type { User } from './types';

export const ACCESS_TOKEN_KEY = 'bugDaddyAccessToken';
export const REFRESH_TOKEN_KEY = 'bugDaddyRefreshToken';
export const USER_KEY = 'bugDaddyUser';
export const VIEW_KEY = 'bugDaddyView';
export const TAB_KEY = 'bugDaddyTab';

export function getStoredUser(): User | null {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function storeSession(accessToken: string, refreshToken: string, user: User) {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}
