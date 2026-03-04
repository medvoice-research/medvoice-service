import { proxyPost } from '@/app/api/medvoice/client';

export async function POST(
  request: Request,
  { params }: { params: Promise<{ route: string[] }> }
): Promise<Response> {
  const { route } = await params;
  const endpoint = route.join('/');

  if (endpoint !== 'login' && endpoint !== 'signup') {
    return new Response(JSON.stringify({ detail: 'Not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const body = await request.text();
  return proxyPost(`/auth/${endpoint}`, body);
}
