import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';

// Reuse a single connection across the application.
// Next.js may create multiple instances in dev mode; singleton pattern avoids leaks.

if (!process.env.POSTGRES_URL) {
    throw new Error('POSTGRES_URL environment variable is not set');
}

export const client = postgres(process.env.POSTGRES_URL);
export const db = drizzle(client, { schema });
