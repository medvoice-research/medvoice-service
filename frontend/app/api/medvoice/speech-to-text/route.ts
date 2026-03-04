import { NextRequest } from 'next/server';
import { proxyFormPost, getBackendUrl } from '../client';

export async function POST(request: NextRequest) {
    const formData = await request.formData();
    const searchParams = request.nextUrl.searchParams.toString();
    const backendPath = `/speech-to-text${searchParams ? `?${searchParams}` : ''}`;

    return proxyFormPost(backendPath, formData);
}
