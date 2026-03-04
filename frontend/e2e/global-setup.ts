/**
 * Playwright Global Setup
 *
 * Registers the two test users via the FastAPI /auth/signup endpoint
 * before any tests run. If users already exist (409), that's fine — we
 * simply proceed.
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
];

async function seedUser(user: TestUser): Promise<void> {
    try {
        const res = await fetch(`${BACKEND_URL}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user),
        });

        if (res.ok) {
            console.log(`[global-setup] Created user: ${user.email}`);
        } else if (res.status === 409) {
            console.log(`[global-setup] User already exists: ${user.email}`);
        } else {
            const body = await res.text();
            console.warn(
                `[global-setup] Unexpected status ${res.status} for ${user.email}: ${body}`,
            );
        }
    } catch (err) {
        console.error(
            `[global-setup] Could not reach backend at ${BACKEND_URL}. Is it running?`,
            err,
        );
        throw err;
    }
}

export default async function globalSetup() {
    console.log('[global-setup] Seeding test users…');
    await Promise.all(TEST_USERS.map(seedUser));
    console.log('[global-setup] Done.');
}
