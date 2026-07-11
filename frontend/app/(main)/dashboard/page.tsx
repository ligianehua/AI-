"use client";

import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useMe } from "@/lib/hooks/use-me";

type Summary = components["schemas"]["DashboardSummary"];

const ROLE_LABELS: Record<string, string> = {
  sales: "销售",
  manager: "主管",
  admin: "管理员",
};

const SCOPE_LABELS: Record<string, string> = {
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
  const { data: me } = useMe();
  const { data: summary } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: async (): Promise<Summary> => {
      const { data, error } = await api.GET("/api/v1/dashboard/summary");
      if (error || !data) throw new Error("加载失败");
      return data;
    },
  });

  const stats = summary
    ? [
        { label: "线索", value: String(summary.lead_count) },
        { label: "客户", value: String(summary.account_count) },
        { label: "商机", value: String(summary.opportunity_count) },
        { label: "在途金额", value: formatCny(summary.pipeline_amount) },
      ]
    : null;

  return (
    <main className="flex-1 py-8">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">工作台</h1>
          {me && (
            <p className="text-sm text-muted-foreground">
              {me.name} · {ROLE_LABELS[me.role]} · 统计范围：{SCOPE_LABELS[me.role]}
            </p>
          )}
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
      </div>
    </main>
  );
}
