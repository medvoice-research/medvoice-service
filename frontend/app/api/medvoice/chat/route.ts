import { NextRequest } from 'next/server';
import { proxyPost } from '../proxy';

/** POST /api/medvoice/chat — medical RAG chat */
export async function POST(request: NextRequest) {
    const body = await request.text();
    return proxyPost('/medical/chat', body);
}
