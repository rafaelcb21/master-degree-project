import { chromium, expect } from '@playwright/test';
import { existsSync } from 'node:fs';
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const browser = await chromium.launch({ headless: true, ...(existsSync(edge) ? { executablePath: edge } : {}) });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(process.env.EXPLORER_URL || 'http://127.0.0.1:8015');
  await expect(page.locator('.hero')).toBeVisible();
  let requests = 0;
  await page.route('**/api/esp32/import', async route => {
    const data = route.request().postDataJSON();
    expect(data.ip).toBe('192.168.0.18');
    requests++;
    await route.fulfill({ status: requests === 1 ? 502 : 201, json: requests === 1 ? { error: 'import_failed' } : {
      folder: 'ESP32/cnn_tflite_esp32/reports/20261006T234046384562Z',
      files: ['ESP32/cnn_tflite_esp32/reports/20261006T234046384562Z/report.csv'], warnings: ['metadata_unavailable']
    }});
  });
  await page.locator('#import-esp32').click();
  await page.locator('#esp32-ip').fill('192.168.0.18');
  await page.locator('#esp32-submit').click();
  await expect(page.locator('#esp32-status')).toContainText('Falha ao importar');
  await page.locator('#esp32-submit').click();
  await expect(page.locator('#esp32-status')).toContainText('CSV salvo');
  await expect(page.locator('#esp32-open')).toBeVisible();
  await page.locator('#esp32-close').click();
  await page.locator('#ui-language').click();
  await expect(page.locator('#import-esp32')).toHaveText('Import from ESP32');
  await page.setViewportSize({width: 390, height: 844});
  await page.locator('#import-esp32').click();
  await expect(page.locator('#esp32-title')).toHaveText('Import from ESP32');
  await expect(page.locator('#esp32-submit')).toBeVisible();
  const bounds = await page.locator('#esp32-dialog').boundingBox();
  expect(bounds.x).toBeGreaterThanOrEqual(0);
  expect(bounds.x + bounds.width).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);
  console.log('ESP32 import UI: retry, CSV warning, PT/EN and mobile passed');
} finally { await browser.close(); }
