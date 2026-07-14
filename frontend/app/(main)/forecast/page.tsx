"use client";

import { ForecastPanel } from "@/components/forecast/forecast-panel";

export default function ForecastPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">销售预测</h1>
      <p className="text-sm text-muted-foreground">
        加权 pipeline = Σ 商机金额 × 阶段赢单概率。趋势外推需要至少 26 期（约两个季度）
        周度快照，数据不足时只展示当前 pipeline 与历史走势——没有数据的预测是玄学。
      </p>
      <ForecastPanel />
    </main>
  );
}
