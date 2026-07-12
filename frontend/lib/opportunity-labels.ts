import type { components } from "@/lib/api/schema";

export type OpportunityStage = components["schemas"]["OpportunityStage"];
export type OpportunityOut = components["schemas"]["OpportunityOut"];
export type KanbanColumn = components["schemas"]["KanbanColumn"];

export const STAGE_LABELS: Record<OpportunityStage, string> = {
  initial: "初步接触",
  need_confirmed: "需求确认",
  proposal: "方案报价",
  negotiation: "商务谈判",
  won: "赢单",
  lost: "输单",
};

export const STAGE_ORDER: OpportunityStage[] = [
  "initial",
  "need_confirmed",
  "proposal",
  "negotiation",
  "won",
  "lost",
];

export const SCENARIO_LABELS: Record<string, string> = {
  opening: "开场",
  discovery: "需求挖掘",
  objection: "异议处理",
  pricing: "价格谈判",
  closing: "促成交",
  retention: "维系",
};

export function formatWan(amount: number): string {
  if (amount >= 10_000) {
    return `¥${(amount / 10_000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })}万`;
  }
  return `¥${amount.toLocaleString("zh-CN")}`;
}
