import type { components } from "@/lib/api/schema";

export type LeadSource = components["schemas"]["LeadSource"];
export type LeadStatus = components["schemas"]["LeadStatus"];

export const SOURCE_LABELS: Record<LeadSource, string> = {
  website: "官网",
  exhibition: "展会",
  referral: "转介绍",
  ads: "广告",
  cold_call: "陌拜",
  other: "其他",
};

export const STATUS_LABELS: Record<LeadStatus, string> = {
  new: "新线索",
  contacted: "已联系",
  qualified: "已确认",
  converted: "已转化",
  invalid: "无效",
};

export const URGENCY_LABELS: Record<string, string> = {
  low: "不紧迫",
  medium: "一般",
  high: "紧迫",
};
