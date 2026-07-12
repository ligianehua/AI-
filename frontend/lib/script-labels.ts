import type { components } from "@/lib/api/schema";

export type ScriptCategory = components["schemas"]["ScriptCategory"];
export type ScriptOut = components["schemas"]["ScriptOut"];

export const CATEGORY_LABELS: Record<ScriptCategory, string> = {
  opening: "开场破冰",
  discovery: "需求挖掘",
  objection: "异议处理",
  pricing: "价格谈判",
  closing: "促成交",
  retention: "客户维系",
};

export const CHANNEL_LABELS: Record<string, string> = {
  wechat: "微信",
  email: "邮件",
  phone: "电话",
};
