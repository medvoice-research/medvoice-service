import { proxyGet } from '../client';

export async function GET() {
    return proxyGet('/admin/database/stats');
}
