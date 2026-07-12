import { defineConfig } from "@playwright/test";

/**
 * E2E 冒烟（5 条主流程）。前置条件：
 * - 后端已起（http://localhost:8000）且已 migrate + seed（含 seed_scripts）
 * - 前端 dev server 已起或由本配置自动拉起
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1, // 共享种子数据，串行执行
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    locale: "zh-CN",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
