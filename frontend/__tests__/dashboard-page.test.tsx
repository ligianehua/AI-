import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/lib/auth", () => ({
  getToken: () => "fake-token",
  clearToken: vi.fn(),
}));

vi.mock("@/lib/api/client", () => ({
  api: {
    GET: vi.fn((path: string) => {
      if (path === "/api/v1/auth/me") {
        return Promise.resolve({
          data: {
            id: "u1",
            name: "李小销",
            email: "sales1@example.com",
            role: "sales",
            team_id: null,
            is_active: true,
            created_at: "2026-07-10T00:00:00Z",
          },
        });
      }
      if (path === "/api/v1/notifications") {
        return Promise.resolve({ data: { items: [], total: 0, page: 1, page_size: 5 } });
      }
      return Promise.resolve({
        data: {
          lead_count: 17,
          account_count: 8,
          opportunity_count: 5,
          pipeline_amount: 1230000,
          won_amount_this_month: 660000,
          funnel: [
            { stage: "initial", count: 3 },
            { stage: "need_confirmed", count: 1 },
            { stage: "proposal", count: 1 },
            { stage: "negotiation", count: 0 },
            { stage: "won", count: 2 },
            { stage: "lost", count: 0 },
          ],
          todos: [
            {
              activity_id: "a1",
              next_action: "回访王总确认报价",
              next_action_date: "2026-07-10",
              related_type: "opportunity",
              related_label: "商机：测试商机",
              overdue: true,
            },
          ],
        },
      });
    }),
  },
}));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import DashboardPage from "@/app/(main)/dashboard/page";

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("工作台", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("展示当前用户与按可见域统计的摘要卡片", async () => {
    renderWithQuery(<DashboardPage />);
    expect(await screen.findByText("工作台")).toBeDefined();
    expect(await screen.findByText(/李小销/)).toBeDefined();
    expect(await screen.findByText("17")).toBeDefined(); // 线索数
    expect(await screen.findByText("8")).toBeDefined(); // 客户数
    expect(await screen.findByText("5")).toBeDefined(); // 商机数
    expect(await screen.findByText(/123.*万/)).toBeDefined(); // 在途金额 ¥123 万
    expect(await screen.findByText(/66.*万/)).toBeDefined(); // 本月成交 ¥66 万
    expect(await screen.findByText("回访王总确认报价")).toBeDefined(); // 今日待办
    expect(screen.getAllByTestId("stat-card")).toHaveLength(5);
  });
});
