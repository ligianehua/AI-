"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { clearToken, getToken } from "@/lib/auth";

type Me = components["schemas"]["UserOut"];
type Summary = components["schemas"]["DashboardSummary"];

const ROLE_LABELS: Record<Me["role"], string> = {
  sales: "销售",
  manager: "主管",
  admin: "管理员",
};

const SCOPE_LABELS: Record<Me["role"], string> = {
  sales: "我的数据",
  manager: "团队数据",
  admin: "全部数据",
};

function formatCny(amount: number): string {
  if (amount >= 10_000) {
    return `¥${(amount / 10_000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 万`;
  }
  return `¥${amount.toLocaleString("zh-CN")}`;
}

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.GET("/api/v1/auth/me").then(({ data, error }) => {
      if (error || !data) {
        clearToken();
        router.replace("/login");
        return;
      }
      setMe(data);
    });
    api.GET("/api/v1/dashboard/summary").then(({ data }) => {
      if (data) setSummary(data);
    });
  }, [router]);

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  if (!me) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground">加载中…</p>
      </main>
    );
  }

  const stats = summary
    ? [
        { label: "线索", value: String(summary.lead_count) },
        { label: "客户", value: String(summary.account_count) },
        { label: "商机", value: String(summary.opportunity_count) },
        { label: "在途金额", value: formatCny(summary.pipeline_amount) },
      ]
    : null;

  return (
    <main className="flex-1 p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">工作台</h1>
            <p className="text-sm text-muted-foreground">
              {me.name} · {ROLE_LABELS[me.role]} · 统计范围：{SCOPE_LABELS[me.role]}
            </p>
          </div>
          <Button variant="outline" onClick={handleLogout}>
            退出登录
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {stats
            ? stats.map((s) => (
                <Card key={s.label} data-testid="stat-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-normal text-muted-foreground">
                      {s.label}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-2xl font-semibold">{s.value}</p>
                  </CardContent>
                </Card>
              ))
            : Array.from({ length: 4 }, (_, i) => (
                <Card key={i} data-testid="stat-skeleton">
                  <CardContent className="py-8">
                    <p className="text-center text-sm text-muted-foreground">加载中…</p>
                  </CardContent>
                </Card>
              ))}
        </div>

        <p className="text-sm text-muted-foreground">
          线索、客户、商机等功能模块将在后续里程碑上线。
        </p>
      </div>
    </main>
  );
}
