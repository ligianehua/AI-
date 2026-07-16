"use client";

import { AdvisorChat } from "@/components/product-advisor/advisor-chat";

export default function ProductAdvisorPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">产品咨询</h1>
      <p className="text-sm text-muted-foreground">
        虚拟销售专家 + 智能运维助手：售前问选型、参数、对比卖点；售后问故障排查、维护保养。
        回答基于产品库真实参数与知识库手册——查不到的绝不编造，需要时会建议转人工工程师。
      </p>
      <AdvisorChat />
    </main>
  );
}
