"use client";

import { CandidatePool } from "@/components/discovery/candidate-pool";
import { SubscriptionPanel } from "@/components/discovery/subscription-panel";

export default function DiscoveryPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">线索发现</h1>
      <p className="text-sm text-muted-foreground">
        选择目标市场（国家 + 城市 + 品类），系统从 Google 地图拉取真实商户进候选池；
        逐条「领取」转为正式线索并自动 AI 评分。
      </p>
      <SubscriptionPanel />
      <CandidatePool />
    </main>
  );
}
