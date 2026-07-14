"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, apiErrorMessage } from "@/lib/api/client";
import { useMe } from "@/lib/hooks/use-me";

const STAGE_LABELS: Record<string, string> = {
  initial: "初步接洽",
  need_confirmed: "需求确认",
  proposal: "方案报价",
  negotiation: "商务谈判",
};

interface StageBucket {
  stage: string;
  amount: number;
  weighted: number;
  count: number;
}

interface ForecastData {
  pipeline: {
    total_amount: number;
    weighted_amount: number;
    open_count: number;
    by_stage: StageBucket[];
  };
  snapshots: { date: string; total_amount: number; weighted_amount: number }[];
  trend: {
    next_weighted: number;
    lower: number;
    upper: number;
    slope_per_period: number;
    method: string;
  } | null;
  data_note: string;
}

function fmtCny(v: number): string {
  if (v >= 10000) return `${(v / 10000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 万`;
  return v.toLocaleString("zh-CN");
}

/** 轻量 SVG 折线图（数据点少；规模大后可换 ECharts） */
function TrendLine({ points }: { points: { date: string; value: number }[] }) {
  if (points.length < 2) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        快照少于 2 期，暂无走势可画。每周一自动生成快照，也可手动生成。
      </p>
    );
  }
  const w = 640;
  const h = 160;
  const pad = 8;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = points.map((p, i) => {
    const x = pad + (i * (w - pad * 2)) / (points.length - 1);
    const y = h - pad - ((p.value - min) * (h - pad * 2)) / span;
    return `${x},${y}`;
  });
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-40 w-full min-w-96">
        <polyline
          points={coords.join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="text-primary"
        />
        {coords.map((c, i) => {
          const [x, y] = c.split(",").map(Number);
          return <circle key={i} cx={x} cy={y} r="3" className="fill-primary" />;
        })}
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {points[0].date}（{fmtCny(points[0].value)}）
        </span>
        <span>
          {points[points.length - 1].date}（{fmtCny(points[points.length - 1].value)}）
        </span>
      </div>
    </div>
  );
}

export function ForecastPanel() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canSnapshot = me?.role === "admin" || me?.role === "manager";

  const { data } = useQuery({
    queryKey: ["forecast"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/forecast");
      if (error || !data) throw new Error("加载预测失败");
      return data as unknown as ForecastData;
    },
  });

  async function handleSnapshot() {
    const { data: resp, error } = await api.POST("/api/v1/forecast/snapshot");
    if (error) {
      toast.error(`提交失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success(String((resp as { message?: string })?.message ?? "已提交"));
    setTimeout(() => queryClient.invalidateQueries({ queryKey: ["forecast"] }), 3000);
  }

  if (!data) return <p className="text-sm text-muted-foreground">加载中…</p>;

  const { pipeline, snapshots, trend, data_note } = data;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">加权 pipeline</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">¥{fmtCny(pipeline.weighted_amount)}</p>
            <p className="text-xs text-muted-foreground">
              未加权合计 ¥{fmtCny(pipeline.total_amount)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">进行中商机</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{pipeline.open_count} 个</p>
            <p className="text-xs text-muted-foreground">won/lost 不计入</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">下期外推</CardTitle>
          </CardHeader>
          <CardContent>
            {trend ? (
              <>
                <p className="text-2xl font-semibold">¥{fmtCny(trend.next_weighted)}</p>
                <p className="text-xs text-muted-foreground">
                  95% 区间 ¥{fmtCny(Math.max(0, trend.lower))} ~ ¥{fmtCny(trend.upper)}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">数据不足，暂不外推</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>阶段分解</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {pipeline.by_stage.map((b) => {
            const ratio =
              pipeline.weighted_amount > 0 ? (b.weighted / pipeline.weighted_amount) * 100 : 0;
            return (
              <div key={b.stage} className="flex items-center gap-3 text-sm">
                <span className="w-20 shrink-0">{STAGE_LABELS[b.stage] ?? b.stage}</span>
                <div className="h-3 flex-1 rounded bg-muted">
                  <div
                    className="h-3 rounded bg-primary/70"
                    style={{ width: `${Math.max(ratio, b.weighted > 0 ? 2 : 0)}%` }}
                  />
                </div>
                <span className="w-40 shrink-0 text-right text-muted-foreground">
                  ¥{fmtCny(b.weighted)}（{b.count} 个）
                </span>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>加权 pipeline 走势（近 {snapshots.length} 期快照）</CardTitle>
          {canSnapshot && (
            <Button variant="outline" size="sm" onClick={handleSnapshot}>
              生成今日快照
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <TrendLine points={snapshots.map((s) => ({ date: s.date, value: s.weighted_amount }))} />
          <p className="mt-2 text-xs text-muted-foreground">{data_note}</p>
        </CardContent>
      </Card>
    </div>
  );
}
