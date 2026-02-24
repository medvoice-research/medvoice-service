import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { jwtVerify } from 'jose';

const protectedRoutes = '/dashboard';

const jwtSecret = new TextEncoder().encode(
  process.env.BACKEND_JWT_SECRET || process.env.AUTH_SECRET || ''
);

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const sessionCookie = request.cookies.get('session');
  const isProtectedRoute = pathname.startsWith(protectedRoutes);

  if (isProtectedRoute && !sessionCookie) {
    return NextResponse.redirect(new URL('/sign-in', request.url));
  }

  if (sessionCookie && request.method === 'GET') {
    try {
      await jwtVerify(sessionCookie.value, jwtSecret, {
        algorithms: ['HS256'],
      });
    } catch {
      const res = NextResponse.next();
      res.cookies.delete('session');
      if (isProtectedRoute) {
        return NextResponse.redirect(new URL('/sign-in', request.url));
      }
      return res;
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
  runtime: 'nodejs'
};
