import { NextRequest } from 'next/server';
import { proxyGet } from '../../proxy';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params;
    return proxyGet(`/temporal/workflow/${id}/result`);
}
