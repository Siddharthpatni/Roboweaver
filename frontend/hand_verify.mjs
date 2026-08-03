import { chromium } from 'playwright';
const outDir = '/private/tmp/claude-501/-Users-siddharthpatni--gemini-antigravity-ide-scratch-roboweaver/36393f9a-0b38-422c-9265-349a9d152f70/scratchpad';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
await page.locator('nav').getByRole('button', { name: 'Digital Twin', exact: true }).click();
await page.waitForTimeout(1000);

const gestures = ['open', 'fist', 'pinch', 'precision grip', 'cylindrical grip'];
for (const gesture of gestures) {
  await page.getByRole('button', { name: gesture, exact: true }).click();
  await page.waitForTimeout(1300);
  await page.screenshot({ path: `${outDir}/handcheck_${gesture.replace(/ /g, '_')}.png` });
}

console.log('ERRORS:', JSON.stringify(errors));
await browser.close();
