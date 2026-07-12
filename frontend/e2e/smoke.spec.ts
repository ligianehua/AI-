import { expect, test, type Page } from "@playwright/test";

/** 5 条主流程冒烟（PLAN §8 M7）。依赖 seed 数据（make seed + seed_scripts）。 */

const runId = Date.now().toString().slice(-6);

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/dashboard");
}

test("1. 登录后工作台显示统计与漏斗", async ({ page }) => {
  await login(page, "sales1@example.com", "password123");
  await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
  await expect(page.getByText("统计范围：我的数据")).toBeVisible();
  await expect(page.getByTestId("stat-card")).toHaveCount(5);
  await expect(page.getByText("商机漏斗")).toBeVisible();
  await expect(page.getByText("今日待办")).toBeVisible();
});

test("2. 新建线索后自动评分（异步 + 轮询刷新）", async ({ page }) => {
  await login(page, "sales1@example.com", "password123");
  await page.getByRole("link", { name: "线索" }).click();
  await page.getByRole("button", { name: "新建线索" }).click();
  await page.fill("#account_name", `E2E测试公司${runId}`);
  await page.fill("#contact_name", "测试联系人");
  await page.fill("#contact_phone", "13900001234");
  await page.fill("#requirement_desc", "需要一套销售管理系统，预算充足，尽快上线");
  await page.getByRole("button", { name: /创建（自动 AI 评分）/ }).click();

  // 新线索未评分排在最后一页 → 用状态筛选缩小范围后应可见
  await expect(page.getByText(/线索已创建|疑似撞单/)).toBeVisible();
  // 评分异步完成后（local 模式数秒内，LLM 无 key 时为规则分）出现在列表（轮询刷新）
  await page.getByRole("link", { name: "客户" }).click();
  await page.getByRole("link", { name: "线索" }).click();
  await expect(async () => {
    // 直接查 API 更稳：分数已写入（前端轮询同源数据）
    const token = await page.evaluate(() => localStorage.getItem("access_token"));
    const resp = await page.request.get(
      `http://localhost:8000/api/v1/leads?page=1&page_size=100&sort=-created_at`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const body = await resp.json();
    const lead = body.items.find(
      (l: { account_name: string }) => l.account_name === `E2E测试公司${runId}`,
    );
    expect(lead).toBeTruthy();
    expect(lead.score).not.toBeNull();
  }).toPass({ timeout: 30_000, intervals: [2000] });
});

test("3. 线索转化生成客户", async ({ page }) => {
  await login(page, "sales1@example.com", "password123");
  await page.getByRole("link", { name: "线索" }).click();
  // 转化上一条用例创建的线索（按分排序可能在后页，逐页查找）
  const row = page.getByRole("row", { name: new RegExp(`E2E测试公司${runId}`) });
  await expect(page.getByRole("table")).toBeVisible();
  for (let i = 0; i < 10; i++) {
    if (await row.isVisible()) break;
    const next = page.getByRole("button", { name: "下一页" });
    if (await next.isDisabled()) break;
    await next.click();
    await page.waitForTimeout(800);
  }
  await expect(row).toBeVisible({ timeout: 10_000 });
  await row.getByRole("button", { name: "转化" }).click();
  await page.getByRole("button", { name: "确认转化" }).click();
  await expect(page.getByText("已转化：客户、联系人、商机已创建")).toBeVisible();

  await page.getByRole("link", { name: "客户" }).click();
  await expect(page.getByRole("link", { name: `E2E测试公司${runId}` })).toBeVisible();
});

test("4. 商机看板与新建商机", async ({ page }) => {
  await login(page, "sales1@example.com", "password123");
  await page.getByRole("link", { name: "商机" }).click();
  for (const stage of ["初步接触", "需求确认", "方案报价", "商务谈判", "赢单", "输单"]) {
    await expect(page.getByText(stage, { exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "新建商机" }).click();
  await page.getByRole("combobox").first().click();
  await page.getByRole("option").first().click();
  await page.fill("#opp_name_new", `E2E商机${runId}`);
  await page.fill("#opp_amount_new", "120000");
  await page.getByRole("button", { name: "创建", exact: true }).click();
  await expect(page.getByText("商机已创建")).toBeVisible();
  await expect(page.getByText(`E2E商机${runId}`)).toBeVisible();
});

test("5. 话术库可见 + admin 管理页", async ({ page }) => {
  await login(page, "sales1@example.com", "password123");
  await page.getByRole("link", { name: "话术" }).click();
  await expect(page.getByText("智能话术推荐")).toBeVisible();
  await expect(page.getByText(/话术库（\d+）/)).toBeVisible();

  // admin 才能看到管理页
  await page.getByRole("button", { name: "退出登录" }).click();
  await login(page, "admin@example.com", "admin123");
  await page.getByRole("link", { name: "管理" }).click();
  await expect(page.getByText(/用户（\d+）/)).toBeVisible();
  await expect(page.getByText(/团队（\d+）/)).toBeVisible();
});
