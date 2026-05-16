import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from './storage';
import { ApiError, apiFetch, apiJson, errorMessage } from './api';

describe('api helpers', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('apiJson throws ApiError with server detail on non-2xx responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'Bad request payload' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    await expect(apiJson('/issues')).rejects.toMatchObject({
      status: 400,
      detail: 'Bad request payload',
    });
  });

  it('apiFetch refreshes access token and retries after 401', async () => {
    localStorage.setItem(REFRESH_TOKEN_KEY, 'refresh-1');
    localStorage.setItem(ACCESS_TOKEN_KEY, 'access-old');

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: 'access-new',
            refresh_token: 'refresh-new',
            token_type: 'bearer',
            user: {
              id: 'u1',
              username: 'tester',
              email: 'tester@example.com',
              full_name: null,
              role: 'admin',
              status: 'active',
              is_email_verified: true,
              last_login_at: null,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        )
      )
      .mockResolvedValueOnce(new Response('ok', { status: 200 }));

    vi.stubGlobal('fetch', fetchMock);

    const response = await apiFetch('/health');
    expect(response.status).toBe(200);
    expect(localStorage.getItem(ACCESS_TOKEN_KEY)).toBe('access-new');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('errorMessage returns readable fallback text for unknown errors', () => {
    expect(errorMessage('failure', 'default error')).toBe('default error');
    expect(errorMessage(new Error('network down'), 'default error')).toBe('network down');
    expect(errorMessage(new ApiError(401, 'Unauthorized'), 'default error')).toBe('Unauthorized');
  });
});
