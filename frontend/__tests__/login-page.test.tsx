import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import LoginPage from "@/app/(auth)/login/page";

describe("登录页", () => {
  it("渲染标题、邮箱/密码输入框和登录按钮", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <LoginPage />
      </QueryClientProvider>,
    );
    expect(screen.getByText("AI 销售助手")).toBeDefined();
    expect(screen.getByLabelText("邮箱")).toBeDefined();
    expect(screen.getByLabelText("密码")).toBeDefined();
    expect(screen.getByRole("button", { name: "登录" })).toBeDefined();
  });
});
