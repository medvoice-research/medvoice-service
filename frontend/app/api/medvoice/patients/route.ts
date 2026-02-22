import { proxyGet } from '../client';

/** GET /api/medvoice/patients — list all patients */
export async function GET() {
    return proxyGet('/admin/patients');
}
