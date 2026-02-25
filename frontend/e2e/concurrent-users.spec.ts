import { test, expect, Browser, BrowserContext, Page } from '@playwright/test';

/**
 * Concurrent Users E2E Test
 *
 * Validates that two users can interact with the MedVoice SaaS app
 * simultaneously without session leakage or data cross-contamination.
 *
 * Each user gets an isolated BrowserContext (separate cookies, storage,
 * sessions) and concurrent actions are triggered via Promise.all.
 */

// ---------------------------------------------------------------------------
// Test user credentials – override via environment variables if needed.
// These are seeded by e2e/global-setup.ts before tests run.
// ---------------------------------------------------------------------------
const USER_A = {
    email: process.env.E2E_USER_A_EMAIL || 'testusera@example.com',
    password: process.env.E2E_USER_A_PASSWORD || 'password123',
};

const USER_B = {
    email: process.env.E2E_USER_B_EMAIL || 'testuserb@example.com',
    password: process.env.E2E_USER_B_PASSWORD || 'password123',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Sign in through the UI form and wait for the dashboard to load. */
async function signInUser(
    page: Page,
    credentials: { email: string; password: string },
) {
    await page.goto('/sign-in');
    await page.waitForSelector('#email', { state: 'visible' });
    await page.locator('#email').fill(credentials.email);
    await page.locator('#password').fill(credentials.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    // Wait for redirect to the dashboard
    await page.waitForURL('**/dashboard**', { timeout: 30_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Concurrent Users', () => {
    let browser: Browser;
    let contextA: BrowserContext;
    let contextB: BrowserContext;
    let pageA: Page;
    let pageB: Page;

    test.beforeAll(async ({ browser: b }) => {
        browser = b;

        // Create two completely isolated browser contexts (like two incognito windows).
        contextA = await browser.newContext();
        contextB = await browser.newContext();
        pageA = await contextA.newPage();
        pageB = await contextB.newPage();

        // Sign users in sequentially to establish sessions.
        // This is setup – the *concurrent* behaviour is tested below.
        await signInUser(pageA, USER_A);
        await signInUser(pageB, USER_B);
    });

    test.afterAll(async () => {
        await contextA.close();
        await contextB.close();
    });

    // ── Test 1: Both users are on the dashboard ─────────────────────────
    test('both users are signed in and on the dashboard', async () => {
        expect(pageA.url()).toContain('/dashboard');
        expect(pageB.url()).toContain('/dashboard');

        await expect(pageA.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
        await expect(pageB.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    });

    // ── Test 2: Sessions are isolated ───────────────────────────────────
    test('session cookies are isolated between users', async () => {
        const cookiesA = await contextA.cookies();
        const cookiesB = await contextB.cookies();

        const sessionA = cookiesA.find((c) => c.name === 'session');
        const sessionB = cookiesB.find((c) => c.name === 'session');

        // Both must have a session cookie
        expect(sessionA).toBeDefined();
        expect(sessionB).toBeDefined();

        // The JWT values must differ (different users)
        expect(sessionA!.value).not.toEqual(sessionB!.value);
    });

    // ── Test 3: Concurrent dashboard data fetches ───────────────────────
    test('concurrent dashboard data loads without errors for both users', async () => {
        // Force-refresh both dashboards at the same time
        await Promise.all([
            pageA.goto('/dashboard'),
            pageB.goto('/dashboard'),
        ]);

        // Both should render the Welcome text
        await expect(
            pageA.getByText('Welcome to MedVoice Clinical Portal'),
        ).toBeVisible();
        await expect(
            pageB.getByText('Welcome to MedVoice Clinical Portal'),
        ).toBeVisible();

        // Neither page should show an uncaught error overlay
        const errorOverlayA = pageA.locator('#__next-build-error, [data-nextjs-error]');
        const errorOverlayB = pageB.locator('#__next-build-error, [data-nextjs-error]');

        await expect(errorOverlayA).toHaveCount(0);
        await expect(errorOverlayB).toHaveCount(0);
    });

    // ── Test 4: Concurrent navigation to different pages ────────────────
    test('users can navigate to different pages concurrently', async () => {
        // User A goes to Patients, User B goes to Consultations – simultaneously
        await Promise.all([
            pageA.goto('/dashboard/patients'),
            pageB.goto('/dashboard/consultations'),
        ]);

        expect(pageA.url()).toContain('/dashboard/patients');
        expect(pageB.url()).toContain('/dashboard/consultations');

        // Each page renders without crashing
        await expect(pageA.locator('body')).not.toBeEmpty();
        await expect(pageB.locator('body')).not.toBeEmpty();
    });
});
