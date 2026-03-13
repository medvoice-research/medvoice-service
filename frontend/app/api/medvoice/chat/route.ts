import { NextRequest } from 'next/server';
import { getBackendUrl } from '../client';
import { cookies } from 'next/headers';

/** POST /api/medvoice/chat — medical RAG chat
 *
 * The FastAPI backend reads query, patient_id_encrypted, and session_id as
 * URL query parameters (not JSON body). This handler parses the incoming
 * JSON body, builds the query-param URL, and proxies the POST to the backend.
 */
export async function POST(request: NextRequest) {
    const { query, patient_id_encrypted, session_id } = await request.json();

    // Build query params matching the backend's FastAPI signature
    const params = new URLSearchParams();
    if (query) params.set('query', query);
    if (patient_id_encrypted) params.set('patient_id_encrypted', patient_id_encrypted);
    if (session_id) params.set('session_id', session_id);

    const url = getBackendUrl(`/medical/chat?${params.toString()}`);

    // Build auth headers
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    try {
        const cookieStore = await cookies();
        const session = cookieStore.get('session');
        if (session?.value) {
            headers['Authorization'] = `Bearer ${session.value}`;
        }
    } catch {
        // cookies() may throw outside of a request context
    }

    try {
        const res = await fetch(url, { method: 'POST', headers });
        const data = await res.text();
        return new Response(data, {
            status: res.status,
            headers: { 'Content-Type': 'application/json' },
        });
    } catch {
        return new Response(
            JSON.stringify({ detail: 'Backend unavailable' }),
            { status: 502, headers: { 'Content-Type': 'application/json' } }
        );
    }
}
