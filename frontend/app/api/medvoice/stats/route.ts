import { proxyGet } from '../proxy';

export async function GET() {
    return proxyGet('/admin/database/stats');
}
