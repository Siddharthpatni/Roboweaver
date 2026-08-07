import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const baseURL = process.env.ROBOWEAVER_VISUAL_BASE_URL ?? 'http://127.0.0.1:3000';
const outputDir = process.env.ROBOWEAVER_VISUAL_OUTPUT ?? 'test-results/visual';
const requireCompiler = process.env.ROBOWEAVER_VISUAL_REQUIRE_COMPILER === '1';
const requireResearch = process.env.ROBOWEAVER_VISUAL_REQUIRE_RESEARCH === '1';
const expectedAccessMode = process.env.ROBOWEAVER_VISUAL_EXPECT_ACCESS_MODE;
const profiles = [
  { name: 'macbook-13', width: 1440, height: 900, deviceScaleFactor: 1 },
  { name: 'desktop-32-qhd', width: 2560, height: 1440, deviceScaleFactor: 1 },
  { name: 'desktop-32-4k', width: 3840, height: 2160, deviceScaleFactor: 1 },
];
const workspaces = [
  'Start here', 'Build a program', 'Choose a robot', 'Plan multiple robots',
  'Test the compiler', 'Research lab', 'Robot library', 'Connect hardware', 'Hand simulator',
  'Capability evidence', 'ROS package library', 'Settings',
];

const slug = (value) => value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const failures = [];

try {
  for (const profile of profiles) {
    const context = await browser.newContext({
      viewport: { width: profile.width, height: profile.height },
      deviceScaleFactor: profile.deviceScaleFactor,
      reducedMotion: 'reduce',
    });
    const page = await context.newPage();
    const runtimeErrors = [];
    page.on('pageerror', (error) => runtimeErrors.push(error.message));
    await page.goto(baseURL, { waitUntil: 'networkidle', timeout: 60_000 });
    if (expectedAccessMode) {
      const access = await page.evaluate(async () => {
        const response = await fetch('/api/access');
        return { status: response.status, body: await response.json() };
      });
      if (access.status !== 200 || access.body.mode !== expectedAccessMode) {
        failures.push(`${profile.name}: access mode mismatch ${JSON.stringify(access)}`);
      }
      if (expectedAccessMode === 'lan') {
        const guarded = await page.evaluate(async () => {
          const response = await fetch('/api/roboweaver/api/discover');
          return { status: response.status, body: await response.json() };
        });
        if (guarded.status !== 403 || guarded.body.error !== 'lan_compiler_only') {
          failures.push(`${profile.name}: LAN discovery guard failed ${JSON.stringify(guarded)}`);
        }
      }
    }

    for (const workspace of workspaces) {
      const button = page.getByRole('button', { name: new RegExp(`^${workspace}(?:\\s|$)`) }).first();
      if (!(await button.count())) {
        failures.push(`${profile.name}/${workspace}: navigation button is missing`);
        continue;
      }
      await button.click();
      await page.waitForTimeout(350);
      const layout = await page.evaluate(() => ({
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        visibleText: document.body.innerText.trim().length,
      }));
      if (layout.documentWidth > layout.viewportWidth + 1 || layout.bodyWidth > layout.viewportWidth + 1) {
        failures.push(`${profile.name}/${workspace}: horizontal overflow ${JSON.stringify(layout)}`);
      }
      if (layout.visibleText < 40) {
        failures.push(`${profile.name}/${workspace}: view rendered almost no visible content`);
      }
      await page.screenshot({
        path: `${outputDir}/${profile.name}-${slug(workspace)}.png`,
        fullPage: true,
        animations: 'disabled',
      });
      if (requireCompiler && workspace === 'Build a program') {
        try {
          await page.getByText('Use one robot', { exact: true }).click();
          await page.getByText('Robot profile', { exact: true }).waitFor();
          await page.getByRole('button', { name: /^Compile and verify/ }).click();
          await page.getByText('Compilation complete', { exact: true }).waitFor({ timeout: 60_000 });
          await page.screenshot({
            path: `${outputDir}/${profile.name}-compiler-result.png`,
            fullPage: true,
            animations: 'disabled',
          });
        } catch {
          const alerts = await page.locator('.compiler-alert').allInnerTexts();
          failures.push(
            `${profile.name}/${workspace}: real compiler did not produce a result` +
            (alerts.length ? ` (${alerts.join(' | ')})` : ''),
          );
          await page.screenshot({
            path: `${outputDir}/${profile.name}-compiler-failure.png`,
            fullPage: true,
            animations: 'disabled',
          });
        }
      }
      if (requireResearch && workspace === 'Research lab') {
        try {
          await page.getByRole('checkbox').uncheck();
          await page.getByRole('button', { name: 'Plan isolated experiment' }).click();
          await page.getByText('climbing_monkey', { exact: true }).waitFor({ timeout: 30_000 });
          await page.screenshot({
            path: `${outputDir}/${profile.name}-research-result.png`,
            fullPage: true,
            animations: 'disabled',
          });
        } catch {
          failures.push(`${profile.name}/${workspace}: bounded research plan did not render`);
        }
      }
    }
    if (runtimeErrors.length) {
      failures.push(`${profile.name}: runtime errors: ${runtimeErrors.join(' | ')}`);
    }
    await context.close();
  }
} finally {
  await browser.close();
}

if (failures.length) {
  throw new Error(`Responsive visual QA failed:\n${failures.join('\n')}`);
}

console.log(`Responsive visual QA passed for ${profiles.map((item) => item.name).join(', ')}`);
