// Playwright config for Three.js holo (GPU flags, FPS, screenshots, a11y, real data)
// Run: npx playwright test   (after npm run test:install-browsers)
const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60 * 1000,
  expect: {
    // Visual regression threshold for per-state screenshots
    toHaveScreenshot: { threshold: 0.2, maxDiffPixels: 800 } // tuned for holo shader variance + 3D jitter
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [ ['list'], ['html', { open: 'never' }] ],
  use: {
    // Headless + GPU for Three.js/WebGL fidelity (swiftshader fallback for CI/headless)
    headless: true,
    launchOptions: {
      args: [
        '--use-gl=swiftshader',           // reliable GPU for shaders/FPS in headless
        '--enable-webgl',
        '--ignore-gpu-blacklist',
        '--disable-gpu-sandbox',
        '--disable-setuid-sandbox',
        '--enable-accelerated-2d-canvas',
        '--no-sandbox'
      ]
    },
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off'
  },
  projects: [
    {
      name: 'chromium-holo',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1400, height: 900 } }
    },
    {
      name: 'mobile-holo',
      use: { ...devices['Pixel 5'], viewport: { width: 390, height: 844 } } // edge mobile
    },
    {
      name: 'perf-holo',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1024, height: 768 } },
      // Dedicated perf project: higher timeout, no video, focus on FPS/draws via __HOLO_TEST + renderer.info
    }
  ]
});