import { describe, it, expect, vi, beforeEach } from 'vitest';

// The cookie store spy — shared across tests.
const mockSet = vi.fn();
const mockCookieStore = { set: mockSet };

// Mock next/headers so cookies() returns our spy store.
vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => mockCookieStore),
}));

// session.ts imports 'server-only' at the top of the import chain. Stub it.
vi.mock('server-only', () => ({}));

// session.ts also imports from @/lib/db/schema. That pulls in drizzle/postgres which
// are not available in the Node test environment. Stub the DB schema module.
vi.mock('@/lib/db/schema', () => ({}));

import { setFastAPISession } from '@/lib/auth/session';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('setFastAPISession', () => {
  it('sets the session cookie with the token value', async () => {
    const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test';
    const exp = Math.floor(Date.now() / 1000) + 8 * 60 * 60; // +8 hours

    await setFastAPISession(token, exp);

    expect(mockSet).toHaveBeenCalledOnce();
    const [name, value] = mockSet.mock.calls[0];
    expect(name).toBe('session');
    expect(value).toBe(token);
  });

  it('converts the unix exp timestamp to a Date for the expires option', async () => {
    const exp = 1_700_000_000; // fixed unix ts
    await setFastAPISession('tok', exp);

    const [, , options] = mockSet.mock.calls[0];
    expect(options.expires).toEqual(new Date(exp * 1000));
  });

  it('sets httpOnly: true', async () => {
    await setFastAPISession('tok', 9999);
    const [, , options] = mockSet.mock.calls[0];
    expect(options.httpOnly).toBe(true);
  });

  it('sets secure: true', async () => {
    await setFastAPISession('tok', 9999);
    const [, , options] = mockSet.mock.calls[0];
    expect(options.secure).toBe(true);
  });

  it('sets sameSite: lax', async () => {
    await setFastAPISession('tok', 9999);
    const [, , options] = mockSet.mock.calls[0];
    expect(options.sameSite).toBe('lax');
  });
});
