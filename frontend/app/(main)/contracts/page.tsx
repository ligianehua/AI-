"use client";

import { ContractPanel } from "@/components/contracts/contract-panel";

export default function ContractsPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">合同</h1>
      <p className="text-sm text-muted-foreground">
        上传合同自动抽取要素并做风险初筛；也可从商机一键生成标准草稿。
        AI 结果仅为提示，不构成法律意见，正式签署前须经法务审核。
      </p>
      <ContractPanel />
    </main>
  );
}
