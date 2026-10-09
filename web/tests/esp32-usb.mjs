import { chromium, expect } from '@playwright/test';
import { existsSync } from 'node:fs';
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const browser = await chromium.launch({headless:true,...(existsSync(edge)?{executablePath:edge}:{})});
const page = await browser.newPage();
const errors=[]; page.on('pageerror', e=>errors.push(e.message));
let ports=[], run=null;
try {
  await page.route('**/api/esp32/ports', route=>route.fulfill({json:{ports}}));
  await page.route('**/api/esp32/status', route=>route.fulfill({json:{run}}));
  await page.route('**/api/esp32/start', async route=>{
    const data=route.request().postDataJSON();
    expect(data).toEqual({action:'restart',port:'COM3',runtime:'tflite',autoImport:true});
    run={status:'running',phase:'monitoring',runtime:'tflite',port:'COM3',logs:['serial output'],reports:[],importStatus:'waiting',ip:null};
    await route.fulfill({status:202,json:{run}});
  });
  await page.route('**/api/esp32/stop', async route=>{
    run={...run,status:'completed'};
    await route.fulfill({json:{run}});
  });
  await page.goto((process.env.EXPLORER_URL || 'http://127.0.0.1:8016')+'/#esp32');
  await expect(page.locator('#board-connection')).toContainText('Nenhuma porta');
  await expect(page.locator('#board-flash')).toBeDisabled();
  await expect(page.locator('#board-restart')).toBeDisabled();
  ports=[{port:'COM3',description:'USB UART'}];
  await page.locator('#board-refresh').click();
  await expect(page.locator('#board-restart')).toBeEnabled();
  await page.locator('#board-restart').click();
  await expect(page.locator('#board-log')).toContainText('serial output');
  await expect(page.locator('#board-flash')).toBeDisabled();
  await page.reload();
  await expect(page.locator('#board-stop')).toBeEnabled();
  await page.locator('#board-stop').click();
  await expect(page.locator('#board-status')).toContainText('Monitor encerrado');
  await page.locator('#ui-language').click();
  await expect(page.locator('#main h1')).toHaveText('Run on ESP32');
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('#board-flash')).toBeVisible();
  expect(errors).toEqual([]);
  console.log('ESP32 USB UI passed: absent board, detect, restart, monitor, reload, stop, PT/EN, mobile');
} finally {await browser.close();}
