/**
 * Playwright Global Setup
 *
 * Registers the test users via the FastAPI /auth/signup endpoint
 * before any tests run. If users already exist (409), that's fine — we
 * simply proceed.
 *
 * Seeds 3 users for data isolation testing:
 *   - User A (physician)  — standard user
 *   - User B (nurse)      — standard user
 *   - User C (admin)      — can see all data
 */

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

interface TestUser {
    email: string;
    password: string;
    full_name: string;
    role: string;
}

const TEST_USERS: TestUser[] = [
    {
        email: process.env.E2E_USER_A_EMAIL || 'testusera@example.com',
        password: process.env.E2E_USER_A_PASSWORD || 'password123',
        full_name: 'Test User A',
        role: 'physician',
    },
    {
        email: process.env.E2E_USER_B_EMAIL || 'testuserb@example.com',
        password: process.env.E2E_USER_B_PASSWORD || 'password123',
        full_name: 'Test User B',
        role: 'nurse',
    },
    {
        email: process.env.E2E_USER_C_EMAIL || 'testuserc@example.com',
        password: process.env.E2E_USER_C_PASSWORD || 'password123',
        full_name: 'Test User C',
        role: 'administrator',
    },
];

async function seedUser(user: TestUser, retries = 3): Promise<void> {
    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            const res = await fetch(`${BACKEND_URL}/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(user),
            });

            if (res.ok) {
                console.log(`[global-setup] Created user: ${user.email}`);
                return;
            } else if (res.status === 409) {
                console.log(`[global-setup] User already exists: ${user.email}`);
                return;
            } else if (res.status === 429 && attempt < retries) {
                console.log(`[global-setup] Rate limited for ${user.email}, retrying in 2s…`);
                await new Promise((r) => setTimeout(r, 2000));
                continue;
            } else {
                const body = await res.text();
                console.warn(
                    `[global-setup] Unexpected status ${res.status} for ${user.email}: ${body}`,
                );
                return;
            }
        } catch (err) {
            console.error(
                `[global-setup] Could not reach backend at ${BACKEND_URL}. Is it running?`,
                err,
            );
            throw err;
        }
    }
}

function sleep(ms: number) {
    return new Promise((r) => setTimeout(r, ms));
}

export default async function globalSetup() {
    console.log('[global-setup] Seeding test users…');
    // Seed sequentially with delays to avoid rate limiting
    for (const user of TEST_USERS) {
        await seedUser(user);
        await sleep(500);
    }
    console.log('[global-setup] Done.');
}
