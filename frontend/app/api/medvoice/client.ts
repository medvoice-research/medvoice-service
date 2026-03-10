/**
 * Shared proxy utility for forwarding requests to the MedVoice FastAPI backend.
 *
 * All proxy functions read the `session` cookie (set by the auth flow) and
 * forward it as an `Authorization: Bearer <token>` header so the backend's
 * AuthMiddleware can identify the authenticated user.
 */

import { cookies } from 'next/headers';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

export function getBackendUrl(path: string): string {
    return `${BACKEND_URL}${path}`;
}

function errorResponse(message: string): Response {
    return new Response(
        JSON.stringify({ detail: message }),
        { status: 502, headers: { 'Content-Type': 'application/json' } }
    );
}

/**
 * Build the common headers for backend requests.
 * Includes the JWT session token as a Bearer token when available.
 */
async function buildHeaders(contentType?: string): Promise<Record<string, string>> {
    const headers: Record<string, string> = {};
    if (contentType) {
        headers['Content-Type'] = contentType;
    }

    try {
        const cookieStore = await cookies();
        const session = cookieStore.get('session');
        if (session?.value) {
            headers['Authorization'] = `Bearer ${session.value}`;
        }
    } catch {
        // cookies() may throw outside of a request context (e.g. during build)
    }

    return headers;
}

/** Proxy a GET request to the backend */
export async function proxyGet(backendPath: string): Promise<Response> {
    try {
        const headers = await buildHeaders('application/json');
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'GET',
            headers,
        });

        const data = await res.text();
        return new Response(data, {
            status: res.status,
            headers: { 'Content-Type': 'application/json' },
        });
    } catch {
        return errorResponse('Backend unavailable');
    }
}

/** Proxy a POST request (JSON body) to the backend */
export async function proxyPost(backendPath: string, body: string): Promise<Response> {
    try {
        const headers = await buildHeaders('application/json');
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'POST',
            headers,
            body,
        });

        const data = await res.text();
        return new Response(data, {
            status: res.status,
            headers: { 'Content-Type': 'application/json' },
        });
    } catch {
        return errorResponse('Backend unavailable');
    }
}

/** Proxy a POST request (FormData) to the backend */
export async function proxyFormPost(backendPath: string, formData: FormData): Promise<Response> {
    try {
        const headers = await buildHeaders();
        // Don't set Content-Type for FormData — fetch sets it automatically with boundary
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'POST',
            headers,
            body: formData,
        });

        const data = await res.text();
        return new Response(data, {
            status: res.status,
            headers: { 'Content-Type': 'application/json' },
        });
    } catch {
        return errorResponse('Backend unavailable');
    }
}
