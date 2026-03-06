import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the proxy module before importing the route handler so that the module
// under test picks up the mock at import time.
vi.mock('@/app/api/medvoice/client', () => ({
  proxyPost: vi.fn(),
}));

import { POST } from '@/app/api/auth/[...route]/route';
import { proxyPost } from '@/app/api/medvoice/client';

const mockProxyPost = vi.mocked(proxyPost);

function makeRequest(body = '{"email":"a@b.com","password":"secret123"}'): Request {
  return new Request('http://localhost/api/auth/login', {
    method: 'POST',
    body,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeParams(segments: string[]): { params: Promise<{ route: string[] }> } {
  return { params: Promise.resolve({ route: segments }) };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POST /api/auth/[...route]', () => {
  it('forwards login to proxyPost and returns its response', async () => {
    const fakeResponse = new Response(JSON.stringify({ access_token: 'tok', exp: 9999 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
    mockProxyPost.mockResolvedValueOnce(fakeResponse);

    const req = makeRequest();
    const res = await POST(req, makeParams(['login']));

    expect(mockProxyPost).toHaveBeenCalledOnce();
    expect(mockProxyPost).toHaveBeenCalledWith(
      '/auth/login',
      '{"email":"a@b.com","password":"secret123"}'
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.access_token).toBe('tok');
  });

  it('forwards signup to proxyPost and returns its response', async () => {
    const signupBody = JSON.stringify({
      email: 'a@b.com',
      password: 'secret123',
      full_name: 'Alice',
      role: 'physician',
    });
    const fakeResponse = new Response(JSON.stringify({ access_token: 'tok2', exp: 9999 }), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
    mockProxyPost.mockResolvedValueOnce(fakeResponse);

    const req = new Request('http://localhost/api/auth/signup', {
      method: 'POST',
      body: signupBody,
      headers: { 'Content-Type': 'application/json' },
    });
    const res = await POST(req, makeParams(['signup']));

    expect(mockProxyPost).toHaveBeenCalledOnce();
    expect(mockProxyPost).toHaveBeenCalledWith('/auth/signup', signupBody);
    expect(res.status).toBe(201);
  });

  it('returns 404 for unknown endpoints', async () => {
    const req = makeRequest();
    const res = await POST(req, makeParams(['reset-password']));

    expect(mockProxyPost).not.toHaveBeenCalled();
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body).toEqual({ detail: 'Not found' });
  });

  it('returns 404 for empty route segment', async () => {
    const req = makeRequest();
    const res = await POST(req, makeParams([]));

    expect(res.status).toBe(404);
  });

  it('propagates error response from proxyPost', async () => {
    const errorResponse = new Response(JSON.stringify({ detail: 'Backend unavailable' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
    mockProxyPost.mockResolvedValueOnce(errorResponse);

    const req = makeRequest();
    const res = await POST(req, makeParams(['login']));

    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.detail).toBe('Backend unavailable');
  });
});
