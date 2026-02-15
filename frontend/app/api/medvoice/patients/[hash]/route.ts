import { NextRequest } from 'next/server';
import { proxyGet } from '../../proxy';

/** GET /api/medvoice/patients/[hash] — get patient info by hash */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ hash: string }> }
) {
    const { hash } = await params;
    return proxyGet(`/admin/patient/hash/${hash}`);
}
