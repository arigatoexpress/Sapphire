import { defineConfig } from '@playwright/test'

export default defineConfig({
    testDir: './tests/visual',
    snapshotPathTemplate: '{testDir}/{testFilePath}-snapshots/{arg}{ext}',
    fullyParallel: false,
    workers: 1,
    retries: 0,
    timeout: 60_000,
    expect: {
        timeout: 15_000,
    },
    use: {
        baseURL: 'http://127.0.0.1:4173',
        headless: true,
        viewport: { width: 1365, height: 900 },
        timezoneId: 'UTC',
    },
    webServer: {
        command: 'npm run build && npm run preview -- --host 127.0.0.1 --port 4173',
        port: 4173,
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
    },
})
