import { chromium, expect } from '@playwright/test';
import { existsSync } from 'node:fs';
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const browser = await chromium.launch({ headless: true, ...(existsSync(edge) ? { executablePath: edge } : {}) });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let run = null;
try {
  const url = process.env.EXPLORER_URL || 'http://127.0.0.1:8015';
  const index = await (await page.request.get(`${url}/api/index`)).json();
  const report = index.entries.find(x => x.kind === 'report' && x.project === 'models/mobilenetv2_alpha035');
  await page.route('**/api/executions', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({model: 'mobilenetv2_alpha035', runtime: 'tflite'});
      run = {model: 'mobilenetv2_alpha035', runtime: 'tflite', status: 'running', startedAt: new Date().toISOString(), finishedAt: null, exitCode: null, reports: [], logs: ['Starting benchmark']};
    }
    await route.fulfill({status: 200, json: {run}});
  });
  await page.goto(`${url}/#execute`);
  await expect(page.locator('#execution-start')).toBeEnabled();
  await page.locator('#execution-model').selectOption('mobilenetv2_alpha035');
  await page.locator('#execution-runtime').selectOption('tflite');
  await page.locator('#execution-start').click();
  await expect(page.locator('#execution-start')).toBeDisabled();
  await expect(page.locator('#execution-log')).toContainText('Starting benchmark');
  await page.reload();
  await expect(page.locator('#execution-status')).toContainText('Em execução');
  await expect(page.locator('#execution-start')).toBeDisabled();
  run = {...run, status: 'completed', exitCode: 0, reports: [report.path], logs: ['Benchmark finished']};
  await expect(page.locator('#execution-start')).toBeEnabled({timeout: 10000});
  await page.locator('#execution-reports a').click();
  await expect(page.locator('#detail-body')).toBeVisible();
  await page.locator('#sidebar a[href="#execute"]').click();
  await page.locator('#ui-language').click();
  await expect(page.locator('#main h1')).toHaveText('Run models');
  await expect(page.locator('#execution-status')).toContainText('Completed');
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('#execution-start')).toBeVisible();
  expect(errors).toEqual([]);
  console.log('Execution UI passed: start, logs, busy state, reload, report links, PT/EN, mobile');
} finally {await browser.close();}
