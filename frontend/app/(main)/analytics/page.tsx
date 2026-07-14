"use client";

import { AnalyticsPanel } from "@/components/analytics/analytics-panel";

export default function AnalyticsPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">业绩分析</h1>
      <p className="text-sm text-muted-foreground">
        本月 vs 上月关键指标（成交按商机进入赢单阶段的时间归属），AI
        归因基于真实聚合数据生成，仅供复盘参考。
      </p>
      <AnalyticsPanel />
    </main>
  );
}
