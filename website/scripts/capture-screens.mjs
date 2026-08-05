#!/usr/bin/env node
/**
 * Captures real product screenshots for the marketing site's "See SEMA in action"
 * carousel, from the actual running dev stack (frontend on :5173). Rerunnable as the
 * product evolves — no placeholders or mocks; if the dev stack isn't reachable this
 * exits with an error instead of producing anything.
 *
 * Usage: node scripts/capture-screens.mjs [--url http://localhost:5173]
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, '..', 'public', 'screens');
const FRONTEND_URL = process.argv.includes('--url')
  ? process.argv[process.argv.indexOf('--url') + 1]
  : 'http://localhost:5173';

async function assertReachable(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!res.ok && res.status >= 500) throw new Error(`HTTP ${res.status}`);
  } catch (err) {
    console.error(
      `\nDev stack not reachable at ${url}.\n` +
        `Start it first (docker compose up -d, or see the repo README) and re-run this script.\n` +
        `(${err.message})\n`,
    );
    process.exit(1);
  }
}

async function forceEnglish(page) {
  // The product's chrome language follows document.documentElement.lang (set from the
  // org's resolved setting on mount, see frontend/src/lib/useUiLang.ts). We wait for the
  // dashboard to render first so this override is the last write, not a value the async
  // org-settings fetch clobbers afterward.
  await page.evaluate(() => {
    document.documentElement.lang = 'en';
  });
  await page.waitForTimeout(300);
}

async function main() {
  await assertReachable(FRONTEND_URL);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  console.log(`Capturing from ${FRONTEND_URL} ...`);

  // 1. Home dashboard (org default language may be Hebrew on first paint --
  // wait on a language-agnostic element, not English copy, before overriding)
  await page.goto(FRONTEND_URL, { waitUntil: 'networkidle' });
  await page.getByRole('textbox').first().waitFor({ timeout: 15000 });
  await forceEnglish(page);
  await page.screenshot({ path: path.join(OUT_DIR, 'home.png') });
  console.log('  home.png');

  // 2. Daily brief -- a focused crop of just that section (its container two
  // levels up from the heading), not the full viewport, so it reads as a
  // distinct shot rather than a near-duplicate of home.png.
  const briefHeading = page.getByText(/DAILY BRIEF/i).first();
  await briefHeading.scrollIntoViewIfNeeded();
  const briefSection = briefHeading.locator('xpath=../../..');
  await page.waitForTimeout(200);
  await briefSection.screenshot({ path: path.join(OUT_DIR, 'brief.png') });
  console.log('  brief.png');

  // 3. A chat answer with a chart + KPI cards (existing seeded conversation, no new LLM call)
  // The sidebar's search is a button that reveals a text input, not an input itself.
  await page.getByRole('button', { name: 'Search conversations' }).click();
  await page.getByPlaceholder(/Search conversations/i).fill('trend');
  await page.getByRole('button', { name: /Show revenue trend by month/i }).first().click();
  await page.getByRole('button', { name: 'Ask about this chart' }).first().waitFor({ timeout: 20000 });
  await forceEnglish(page);
  await page.waitForTimeout(200);
  await page.screenshot({ path: path.join(OUT_DIR, 'answer.png') });
  console.log('  answer.png');

  // 4. Admin: users and permissions
  // This table is real org data with real email addresses (including the
  // developer's own) -- redact any leaf-node text that looks like an email
  // before capturing, so nobody's personal address ends up on the public site.
  await page.getByRole('button', { name: 'Admin menu' }).click();
  await page.getByText('Manage organization').click();
  await page.getByRole('heading', { name: 'Users and permissions' }).waitFor({ timeout: 15000 });
  await forceEnglish(page);
  await page.evaluate(() => {
    const emailPattern = /[^\s@]+@[^\s@]+\.[^\s@]+/;
    document.querySelectorAll('body *').forEach((el) => {
      if (el.children.length === 0 && emailPattern.test(el.textContent.trim())) {
        el.textContent = '••••••••••••';
      }
    });
  });
  await page.waitForTimeout(100);
  await page.screenshot({ path: path.join(OUT_DIR, 'admin-users.png') });
  console.log('  admin-users.png');

  // 5. Admin: semantic model
  await page.getByText('Semantic model', { exact: true }).click();
  await page.getByRole('heading', { name: 'Semantic model' }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT_DIR, 'admin-semantic.png') });
  console.log('  admin-semantic.png');

  await browser.close();
  console.log(`\nDone. Screenshots written to ${OUT_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
