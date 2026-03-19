#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let chromium;
try {
  ({ chromium } = require('../sapphire-web/node_modules/playwright'));
} catch (_) {
  ({ chromium } = require('playwright'));
}

const [domainArg, outDirArg, authUserArg, authPassArg] = process.argv.slice(2);
const domain = (domainArg || 'https://sapphirealpha.xyz').replace(/\/+$/, '');
const outDir = outDirArg || path.resolve(process.cwd(), 'output/frontend-visual/current');
const authUser = authUserArg || '';
const authPass = authPassArg || '';

const pages = [
  {
    name: 'overview',
    path: '/',
    waitSelector: '#mission-status',
    clipHeight: 320,
    mask: [
      '#mission-status',
      '#radar-canvas',
      '#price-ticker',
      '#price-chart',
      '#intel-pulse',
      '#market-drivers',
      '#service-list',
      '#execution-kpis',
      '#execution-intel-feed',
      '#execution-context',
      '#activity-log',
      '#radar',
      '#radar-timestamp',
    ],
  },
  {
    name: 'architecture',
    path: '/architecture',
    waitSelector: '#topology-svg',
    clipHeight: 340,
    mask: [
      '#node-layer',
      '#edge-layer',
      '#packet-layer',
      '#pipeline-list',
      '#event-list',
      '#brief-list',
      '#bottleneck-list',
      '#arch-total-services',
      '#arch-online',
      '#arch-active-flows',
      '#arch-signal-rate',
      '#arch-throughput',
      '#arch-health-ratio',
      '#topology-window',
    ],
  },
];

fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 940 },
  timezoneId: 'UTC',
  ...(authUser && authPass ? { httpCredentials: { username: authUser, password: authPass } } : {}),
});

try {
  for (const pageDef of pages) {
    const page = await context.newPage();
    await page.goto(`${domain}${pageDef.path}`, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForSelector(pageDef.waitSelector, { timeout: 20000 });
    await page.evaluate(() => (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()));
    await page.waitForTimeout(1400);

    const masks = [];
    for (const selector of pageDef.mask) {
      const locator = page.locator(selector);
      if ((await locator.count()) > 0) {
        masks.push(locator.first());
      }
    }

    const outPath = path.join(outDir, `${pageDef.name}.png`);
    await page.screenshot({
      path: outPath,
      fullPage: false,
      animations: 'disabled',
      clip: { x: 0, y: 0, width: 1440, height: pageDef.clipHeight || 320 },
      mask: masks,
    });
    await page.close();
    console.log(`captured ${pageDef.name} -> ${outPath}`);
  }
} finally {
  await context.close();
  await browser.close();
}
