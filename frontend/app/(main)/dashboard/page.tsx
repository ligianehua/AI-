"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useMe } from "@/lib/hooks/use-me";
import { STAGE_LABELS } from "@/lib/opportunity-labels";

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
  const { data: notifications } = useQuery({
    queryKey: ["dashboard-notifications"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/notifications", {
        params: { query: { unread_only: true, page: 1, page_size: 5 } },
      });
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
        { label: "本月成交", value: formatCny(summary.won_amount_this_month) },
      ]
    : null;

  const funnelMax = Math.max(1, ...(summary?.funnel.map((f) => f.count) ?? [1]));

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

        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {(stats ?? Array.from({ length: 5 }, () => null)).map((s, i) =>
            s ? (
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
            ) : (
              <Card key={i} data-testid="stat-skeleton">
                <CardContent className="py-8">
                  <p className="text-center text-sm text-muted-foreground">…</p>
                </CardContent>
              </Card>
            ),
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>今日待办（{summary?.todos.length ?? 0}）</CardTitle>
            </CardHeader>
            <CardContent>
              {summary?.todos.length === 0 ? (
                <p className="text-sm text-muted-foreground">没有到期的下一步行动 🎉</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {(summary?.todos ?? []).map((t) => (
                    <li key={t.activity_id} className="flex items-start gap-2">
                      <Badge
                        variant={t.overdue ? "destructive" : "secondary"}
                        className="mt-0.5 shrink-0"
                      >
                        {t.overdue ? "逾期" : "今日"}
                      </Badge>
                      <div>
                        <p>{t.next_action}</p>
                        <p className="text-xs text-muted-foreground">
                          {t.related_label} · {t.next_action_date}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>商机漏斗</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {(summary?.funnel ?? []).map((f) => (
                  <li key={f.stage} className="flex items-center gap-2 text-sm">
                    <span className="w-16 shrink-0 text-muted-foreground">
                      {STAGE_LABELS[f.stage]}
                    </span>
                    <div className="h-4 flex-1 overflow-hidden rounded bg-muted">
                      <div
                        className="h-full rounded bg-primary/70"
                        style={{ width: `${(f.count / funnelMax) * 100}%` }}
                      />
                    </div>
                    <span className="w-6 text-right font-medium">{f.count}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>风险提醒（未读 {notifications?.total ?? 0}）</CardTitle>
            </CardHeader>
            <CardContent>
              {notifications?.items.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无未读提醒</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {(notifications?.items ?? []).map((n) => (
                    <li key={n.id} className="truncate" title={n.title}>
                      • {n.title}
                    </li>
                  ))}
                </ul>
              )}
              <Link
                href="/opportunities"
                className="mt-2 inline-block text-xs text-muted-foreground underline"
              >
                去看板处理 →
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
