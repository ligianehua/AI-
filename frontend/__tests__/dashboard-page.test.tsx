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
      return Promise.resolve({
        data: {
          lead_count: 17,
          account_count: 8,
          opportunity_count: 5,
          pipeline_amount: 1230000,
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
    expect(screen.getAllByTestId("stat-card")).toHaveLength(4);
  });
});
