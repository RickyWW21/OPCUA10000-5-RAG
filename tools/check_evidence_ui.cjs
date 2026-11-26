// Run against the dev servers with Playwright available via PLAYWRIGHT_MODULE.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.goto(process.env.UI_URL || 'http://127.0.0.1:5173')
    await page.locator('.conversation-item.active').waitFor({ timeout: 10000 })
    await page.locator('textarea').fill('ServerType')
    assert.equal(await page.getByRole('button', { name: /^Ask/ }).isEnabled(), true)
    await page.getByRole('button', { name: /^Ask/ }).click()
    await page.locator('.spec-group').waitFor()
    assert.equal(await page.locator('.wiki-group').count(), 0)
    assert.match(await page.locator('.spec-group').innerText(), /1\.05\.06.*|L221-L302/s)
    const specButton = page.locator('.message.assistant .answer-citation').filter({ hasText: '[E1]' }).first()
    await specButton.click()
    const dialog = page.getByRole('dialog')
    await dialog.locator('.numbered-source').waitFor()
    assert.match(await dialog.innerText(), /规范原文/)
    const firstLine = Number(await dialog.locator('.line-number').first().innerText())
    const lastLine = Number(await dialog.locator('.line-number').last().innerText())
    assert.ok(Number.isInteger(firstLine) && firstLine >= 1)
    assert.ok(Number.isInteger(lastLine) && lastLine >= firstLine)
    const actualLines = await dialog.locator('.line-text').allTextContents()
    const sourceLines = fs.readFileSync(path.join(__dirname, '../source/OPC-10000-5-v1.05.06.md'), 'utf8').split(/\r?\n/)
    assert.deepEqual(actualLines, sourceLines.slice(firstLine - 1, lastLine).map((line) => line || ' '))
    await page.screenshot({ path: path.join(__dirname, '../docs/evidence-desktop.png') })
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })
    assert.equal(await specButton.evaluate((element) => element === document.activeElement), true)

    await page.reload()
    await page.locator('.spec-group').waitFor()
    await page.locator('.spec-group .location-button').first().click()
    await dialog.locator('.numbered-source').waitFor()
    await page.keyboard.press('Escape')
    await dialog.waitFor({ state: 'hidden' })

    await page.setViewportSize({ width: 390, height: 844 })
    await page.locator('.spec-group .location-button').first().click()
    await dialog.locator('.numbered-source').waitFor()
    await page.screenshot({ path: path.join(__dirname, '../docs/evidence-mobile.png') })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true)
    const box = await dialog.boundingBox()
    assert.ok(box && box.x >= 0 && box.x + box.width <= 391)
    await dialog.getByRole('button', { name: '关闭来源查看器' }).click()
    await dialog.waitFor({ state: 'hidden' })

    await page.route('**/api/v1/content?**', (route) => route.fulfill({
      status: 503, contentType: 'application/json', body: '{"detail":"Temporary source error"}',
    }))
    await page.locator('.spec-group .location-button').first().click()
    await dialog.getByRole('alert').waitFor()
    assert.match(await dialog.getByRole('alert').innerText(), /Temporary source error/)
    await page.unroute('**/api/v1/content?**')
    await dialog.getByRole('button', { name: '重试', exact: true }).click()
    await dialog.locator('.numbered-source').waitFor()
    await dialog.getByRole('button', { name: '关闭来源查看器' }).click()
    await dialog.waitFor({ state: 'hidden' })
    assert.deepEqual(errors, [])
    console.log('PASS: initial session, spec-only citations, exact source lines, history, Escape/focus, desktop/mobile, error/retry')
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
