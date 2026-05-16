import { describe, expect, it, beforeEach } from 'vitest';

import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  USER_KEY,
  clearSession,
  getStoredUser,
  storeSession,
} from './storage';

const sampleUser = {
  id: 'u1',
  username: 'tester',
  email: 'tester@example.com',
  full_name: 'Test User',
  role: 'admin',
  status: 'active',
  is_email_verified: true,
  last_login_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('storage helpers', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores and reads session user data', () => {
    storeSession('access-1', 'refresh-1', sampleUser);

    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('access-1');
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBe('refresh-1');
    expect(getStoredUser()).toEqual(sampleUser);
  });

  it('returns null for malformed stored user json', () => {
    localStorage.setItem(USER_KEY, '{"bad_json"');
    expect(getStoredUser()).toBeNull();
  });

  it('clears stored session keys', () => {
    storeSession('access-2', 'refresh-2', sampleUser);
    clearSession();

    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });
});
