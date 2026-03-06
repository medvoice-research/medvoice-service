/**
 * Shared proxy utility for forwarding requests to the MedVoice FastAPI backend.
 */

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

/** Proxy a GET request to the backend */
export async function proxyGet(backendPath: string): Promise<Response> {
    try {
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
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
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
        const res = await fetch(getBackendUrl(backendPath), {
            method: 'POST',
            body: formData,
            // Don't set Content-Type for FormData — fetch sets it automatically with boundary
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
