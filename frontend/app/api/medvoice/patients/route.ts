import { proxyGet } from '../proxy';

/** GET /api/medvoice/patients — list all patients */
export async function GET() {
    return proxyGet('/admin/patients');
}
