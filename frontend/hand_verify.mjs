import { chromium } from 'playwright';
const outDir = '/private/tmp/claude-501/-Users-siddharthpatni--gemini-antigravity-ide-scratch-roboweaver/0f1e833a-c56e-40c6-9f2f-ae9ddbb12264/scratchpad';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' });
await page.getByTitle('Digital Twin', { exact: true }).click({ timeout: 5000 });
await page.waitForTimeout(1200);

const gestures = ['open', 'fist', 'pinch', 'precision grip'];
for (const gesture of gestures) {
  await page.locator('button', { hasText: gesture }).first().click({ timeout: 5000 });
  await page.waitForTimeout(1300);
  const canvas = page.locator('canvas').first();
  await canvas.screenshot({ path: `${outDir}/handcheck_${gesture.replace(/ /g, '_')}.png` });
}

console.log('ERRORS:', JSON.stringify(errors));
await browser.close();
