import { test, expect } from '@playwright/test';

test('homepage loads successfully', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL('http://web:8000/');
});

test('homepage body is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('body')).toBeVisible();
});