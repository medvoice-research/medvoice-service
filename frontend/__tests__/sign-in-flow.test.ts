import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Heavy module stubs (must come before the import under test) ────────────

// server-only guard
vi.mock('server-only', () => ({}));

// drizzle DB + schema — not used in signIn/signUp but imported transitively
vi.mock('@/lib/db/drizzle', () => ({ db: {} }));
vi.mock('@/lib/db/schema', () => ({
  users: {},
  teams: {},
  teamMembers: {},
  activityLogs: {},
  invitations: {},
  ActivityType: {},
}));
vi.mock('@/lib/db/queries', () => ({
  getUser: vi.fn(),
  getUserWithTeam: vi.fn(),
}));

// next/headers — cookies() used by setFastAPISession
const mockCookiesSet = vi.fn();
vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({ set: mockCookiesSet, delete: vi.fn() })),
}));

// next/navigation — redirect throws a special Next error in tests; capture it
const mockRedirect = vi.fn((url: string) => {
  // Simulate Next.js redirect by throwing so the action stops — matching real behavior.
  throw new Error(`NEXT_REDIRECT:${url}`);
});
vi.mock('next/navigation', () => ({
  redirect: (url: string) => mockRedirect(url),
}));

// ── Now import the actions ─────────────────────────────────────────────────
import { signIn, signUp } from '@/app/(login)/actions';

// ── Helpers ────────────────────────────────────────────────────────────────

function makeFormData(fields: Record<string, string>): FormData {
  const fd = new FormData();
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  return fd;
}

const VALID_LOGIN = { email: 'alice@example.com', password: 'password123' };
const VALID_SIGNUP = {
  email: 'alice@example.com',
  password: 'password123',
  full_name: 'Alice Smith',
  role: 'physician',
};

const ACCESS_TOKEN = 'eyJ.test.token';
const EXP = Math.floor(Date.now() / 1000) + 8 * 3600;

beforeEach(() => {
  vi.clearAllMocks();
  // Default: stub global fetch to return a successful login response
  vi.stubGlobal('fetch', vi.fn());
});

// ── signIn ─────────────────────────────────────────────────────────────────

describe('signIn', () => {
  it('calls setFastAPISession and redirects on success', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: ACCESS_TOKEN, exp: EXP }), { status: 200 })
    );

    let thrownUrl: string | null = null;
    try {
      await signIn({}, makeFormData(VALID_LOGIN));
    } catch (e: unknown) {
      if (e instanceof Error && e.message.startsWith('NEXT_REDIRECT:')) {
        thrownUrl = e.message.replace('NEXT_REDIRECT:', '');
      } else {
        throw e;
      }
    }

    expect(mockCookiesSet).toHaveBeenCalledOnce();
    const [name, token, opts] = mockCookiesSet.mock.calls[0];
    expect(name).toBe('session');
    expect(token).toBe(ACCESS_TOKEN);
    expect(opts.expires).toEqual(new Date(EXP * 1000));
    expect(opts.httpOnly).toBe(true);

    expect(thrownUrl).toBe('/dashboard');
  });

  it('returns an error object on 401', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Invalid email or password.' }), { status: 401 })
    );

    const result = await signIn({}, makeFormData(VALID_LOGIN));

    expect(result).toMatchObject({ error: 'Invalid email or password.' });
    expect(mockCookiesSet).not.toHaveBeenCalled();
    expect(mockRedirect).not.toHaveBeenCalled();
  });

  it('returns a generic error message on non-string detail', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: ['field error'] }), { status: 422 })
    );

    const result = await signIn({}, makeFormData(VALID_LOGIN));
    expect(result).toMatchObject({ error: 'Invalid email or password. Please try again.' });
  });

  it('returns a network error when fetch throws', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('fetch failed'));

    const result = await signIn({}, makeFormData(VALID_LOGIN));
    expect(result).toMatchObject({ error: expect.stringContaining('Unable to reach') });
  });

  it('returns a validation error for invalid email', async () => {
    const result = await signIn({}, makeFormData({ email: 'not-an-email', password: 'password123' }));
    expect(result).toMatchObject({ error: expect.any(String) });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('returns a validation error for short password', async () => {
    const result = await signIn({}, makeFormData({ email: 'a@b.com', password: 'short' }));
    expect(result).toMatchObject({ error: expect.any(String) });
    expect(fetch).not.toHaveBeenCalled();
  });
});

// ── signUp ─────────────────────────────────────────────────────────────────

describe('signUp', () => {
  it('calls setFastAPISession and redirects on success', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: ACCESS_TOKEN, exp: EXP }), { status: 201 })
    );

    let thrownUrl: string | null = null;
    try {
      await signUp({}, makeFormData(VALID_SIGNUP));
    } catch (e: unknown) {
      if (e instanceof Error && e.message.startsWith('NEXT_REDIRECT:')) {
        thrownUrl = e.message.replace('NEXT_REDIRECT:', '');
      } else {
        throw e;
      }
    }

    expect(mockCookiesSet).toHaveBeenCalledOnce();
    const [name, token] = mockCookiesSet.mock.calls[0];
    expect(name).toBe('session');
    expect(token).toBe(ACCESS_TOKEN);
    expect(thrownUrl).toBe('/dashboard');
  });

  it('returns an error object on 409 conflict', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Email already registered.' }), { status: 409 })
    );

    const result = await signUp({}, makeFormData(VALID_SIGNUP));
    expect(result).toMatchObject({ error: 'Email already registered.' });
    expect(mockCookiesSet).not.toHaveBeenCalled();
  });

  it('returns a network error when fetch throws', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('ECONNREFUSED'));

    const result = await signUp({}, makeFormData(VALID_SIGNUP));
    expect(result).toMatchObject({ error: expect.stringContaining('Unable to reach') });
  });

  it('returns a validation error when role is invalid', async () => {
    const result = await signUp(
      {},
      makeFormData({ ...VALID_SIGNUP, role: 'hacker' })
    );
    expect(result).toMatchObject({ error: expect.any(String) });
    expect(fetch).not.toHaveBeenCalled();
  });

  it('returns a validation error when full_name is missing', async () => {
    const { full_name: _, ...noName } = VALID_SIGNUP;
    const result = await signUp({}, makeFormData(noName as Record<string, string>));
    expect(result).toMatchObject({ error: expect.any(String) });
    expect(fetch).not.toHaveBeenCalled();
  });
});
