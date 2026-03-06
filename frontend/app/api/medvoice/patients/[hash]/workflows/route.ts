import { NextRequest } from 'next/server';
import { proxyGet } from '../../../client';

/** GET /api/medvoice/patients/[hash]/workflows — get patient's workflows */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ hash: string }> }
) {
    const { hash } = await params;
    const searchParams = request.nextUrl.searchParams;
    const status = searchParams.get('status');
    const limit = searchParams.get('limit') || '20';
    const offset = searchParams.get('offset') || '0';

    let backendPath = `/temporal/patient/${hash}/workflows?limit=${limit}&offset=${offset}`;
    if (status) backendPath += `&status=${status}`;

    return proxyGet(backendPath);
}
