"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, apiErrorMessage } from "@/lib/api/client";

interface MonthMetrics {
  month: string;
  won_amount: number;
  won_count: number;
  lost_count: number;
  win_rate: number | null;
  avg_cycle_days: number | null;
  activity_count: number;
  new_leads: number;
}

interface PerformanceData {
  scope: string;
  current: MonthMetrics;
  previous: MonthMetrics;
}

interface Insight {
  summary: string;
  findings: string[];
  suggestions: string[];
}

function fmtCny(v: number): string {
  if (v >= 10000) return `${(v / 10000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 万`;
  return v.toLocaleString("zh-CN");
}

function Delta({ cur, prev, invert = false }: { cur: number | null; prev: number | null; invert?: boolean }) {
  if (cur === null || prev === null) return null;
  const diff = cur - prev;
  if (diff === 0) return <span className="text-xs text-muted-foreground">持平</span>;
  const better = invert ? diff < 0 : diff > 0;
  return (
    <span className={`text-xs ${better ? "text-green-600" : "text-red-600"}`}>
      {diff > 0 ? "↑" : "↓"} {Math.abs(Math.round(diff * 10) / 10).toLocaleString("zh-CN")}
    </span>
  );
}

export function AnalyticsPanel() {
  const [insight, setInsight] = useState<Insight | null>(null);
  const [generating, setGenerating] = useState(false);

  const { data } = useQuery({
    queryKey: ["analytics-performance"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/analytics/performance");
      if (error || !data) throw new Error("加载业绩失败");
      return data as unknown as PerformanceData;
    },
  });

  async function handleInsight() {
    setGenerating(true);
    setInsight(null);
    try {
      const { data: resp, error } = await api.POST("/api/v1/analytics/insight");
      if (error || !resp) {
        toast.error(`生成失败：${apiErrorMessage(error)}`);
        return;
      }
      setInsight(resp as unknown as Insight);
    } finally {
      setGenerating(false);
    }
  }

  if (!data) return <p className="text-sm text-muted-foreground">加载中…</p>;

  const { current: cur, previous: prev } = data;
  const cards: {
    label: string;
    value: string;
    delta: React.ReactNode;
    sub?: string;
  }[] = [
    {
      label: "成交额",
      value: `¥${fmtCny(cur.won_amount)}`,
      delta: <Delta cur={cur.won_amount} prev={prev.won_amount} />,
      sub: `上月 ¥${fmtCny(prev.won_amount)}`,
    },
    {
      label: "赢单 / 丢单",
      value: `${cur.won_count} / ${cur.lost_count}`,
      delta: <Delta cur={cur.won_count} prev={prev.won_count} />,
      sub: `上月 ${prev.won_count} / ${prev.lost_count}`,
    },
    {
      label: "赢率",
      value: cur.win_rate === null ? "无关闭商机" : `${cur.win_rate}%`,
      delta: <Delta cur={cur.win_rate} prev={prev.win_rate} />,
      sub: prev.win_rate === null ? "上月无关闭商机" : `上月 ${prev.win_rate}%`,
    },
    {
      label: "平均成交周期",
      value: cur.avg_cycle_days === null ? "—" : `${cur.avg_cycle_days} 天`,
      delta: <Delta cur={cur.avg_cycle_days} prev={prev.avg_cycle_days} invert />,
      sub: prev.avg_cycle_days === null ? "上月无赢单" : `上月 ${prev.avg_cycle_days} 天`,
    },
    {
      label: "跟进活动",
      value: `${cur.activity_count} 次`,
      delta: <Delta cur={cur.activity_count} prev={prev.activity_count} />,
      sub: `上月 ${prev.activity_count} 次`,
    },
    {
      label: "新增线索",
      value: `${cur.new_leads} 条`,
      delta: <Delta cur={cur.new_leads} prev={prev.new_leads} />,
      sub: `上月 ${prev.new_leads} 条`,
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        视角：{data.scope}（{cur.month} vs {prev.month}）
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        {cards.map((c) => (
          <Card key={c.label}>
            <CardHeader>
              <CardTitle className="text-sm text-muted-foreground">{c.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-baseline gap-2">
                <p className="text-2xl font-semibold">{c.value}</p>
                {c.delta}
              </div>
              {c.sub && <p className="text-xs text-muted-foreground">{c.sub}</p>}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>AI 月度归因</CardTitle>
          <Button size="sm" disabled={generating} onClick={handleInsight}>
            {generating ? "分析中…" : "生成解读"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {!insight && !generating && (
            <p className="text-muted-foreground">
              点「生成解读」让 AI 基于上面的真实指标做归因分析（约需 10 秒）。
            </p>
          )}
          {generating && <p className="animate-pulse text-muted-foreground">正在分析指标…</p>}
          {insight && (
            <>
              <p>{insight.summary}</p>
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">归因发现</p>
                <ul className="list-inside list-disc space-y-0.5">
                  {insight.findings.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">下月建议</p>
                <ul className="list-inside list-disc space-y-0.5">
                  {insight.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-muted-foreground">归因为 AI 推断，仅供复盘参考。</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
