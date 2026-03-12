import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright-core";

const REPO_ROOT = path.resolve(fileURLToPath(new URL("..", import.meta.url)));

test("inline history heat selector updates the selected day and activities", async (t) => {
  const browserExecutablePath = await resolveBrowserExecutablePath();
  if (!browserExecutablePath) {
    t.skip("Chrome or Edge not available for browser integration test.");
    return;
  }

  const server = http.createServer(async (request, response) => {
    try {
      const requestPath = new URL(request.url, "http://127.0.0.1").pathname;
      const relativePath = requestPath === "/" ? "/tests/fixtures/analysis-history-flow.html" : requestPath;
      const safePath = path.normalize(relativePath).replace(/^([/\\])+/, "");
      const filePath = path.join(REPO_ROOT, safePath);
      if (!filePath.startsWith(REPO_ROOT)) {
        response.writeHead(403);
        response.end("Forbidden");
        return;
      }

      const content = await fs.readFile(filePath);
      response.writeHead(200, { "Content-Type": contentTypeFor(filePath) });
      response.end(content);
    } catch (_error) {
      response.writeHead(404);
      response.end("Not found");
    }
  });

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

  const address = server.address();
  assert(address && typeof address === "object");
  const baseUrl = `http://127.0.0.1:${address.port}`;

  const browser = await chromium.launch({
    executablePath: browserExecutablePath,
    headless: true,
  });

  try {
    const page = await browser.newPage();
    await page.goto(`${baseUrl}/tests/fixtures/analysis-history-flow.html`);

    await page.waitForSelector("#historyTable .history-row");
    await assertHistoryState(page, "2026-03-12", "2026-03-12");

    await page.locator('.history-heat-cell[data-day="2026-03-11"]').click();

    await assertHistoryState(page, "2026-03-11", "2026-03-11");
    assert.notEqual(await page.locator("#activityHeadline").textContent(), "Activities On 2026-03-12");
    await assert.equal(await page.locator("#activitySelectionMeta").textContent(), "Selected in History: 2026-03-11");
  } finally {
    await browser.close();
    await new Promise((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
  }
});

async function assertHistoryState(page, activeDay, activityDay) {
  const activeRowCount = await page.locator(`#historyTable .history-row.is-active[data-day="${activeDay}"]`).count();
  assert.equal(activeRowCount, 1);
  assert.equal(await page.locator(`#historyTable .history-heat-cell.is-active[data-day="${activeDay}"]`).count(), 1);
  assert.equal(await page.locator("#activityHeadline").textContent(), `Activities On ${activityDay}`);

  if (activityDay === "2026-03-11") {
    assert.equal(await page.locator("#activityList .activity-card").count(), 1);
    await page.locator("#activityList").waitFor();
    assert.match(await page.locator("#activityList").textContent(), /Steady Ride/);
    assert.equal(await page.locator('#historyTable .history-row.is-active[data-day="2026-03-12"]').count(), 0);
  }
}

async function resolveBrowserExecutablePath() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROME_EXECUTABLE,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      return candidate;
    } catch (_error) {
      // Try the next browser candidate.
    }
  }
  return null;
}

function contentTypeFor(filePath) {
  switch (path.extname(filePath).toLowerCase()) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
    case ".mjs":
      return "application/javascript; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    default:
      return "text/plain; charset=utf-8";
  }
}
