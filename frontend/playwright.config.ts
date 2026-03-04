import { defineConfig } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    globalSetup: './e2e/global-setup.ts',
    timeout: 60_000,
    retries: 0,
    use: {
        baseURL: process.env.BASE_URL || 'http://localhost:3000',
        headless: true,
        screenshot: 'only-on-failure',
        trace: 'retain-on-failure',
    },
    projects: [
        {
            name: 'chromium',
            use: { browserName: 'chromium' },
        },
    ],
});
