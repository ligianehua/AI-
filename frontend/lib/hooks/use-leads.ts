"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type LeadOut = components["schemas"]["LeadOut"];
export type LeadStatus = components["schemas"]["LeadStatus"];

export interface LeadFilters {
  page: number;
  status: LeadStatus | "all";
  sort: string;
}

export function useLeads(filters: LeadFilters) {
  return useQuery({
    queryKey: ["leads", filters],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/leads", {
        params: {
          query: {
            page: filters.page,
            page_size: 20,
            sort: filters.sort,
            ...(filters.status !== "all" ? { status: filters.status } : {}),
          },
        },
      });
      if (error || !data) throw new Error("加载线索失败");
      return data;
    },
    // 有"评分中"的线索时轮询刷新（评分异步完成后列表自动更新）。
    // 只对 10 分钟内创建的未评分线索轮询，避免历史未评分数据导致无限轮询。
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      const now = Date.now();
      const scoring = items?.some(
        (l) =>
          l.score === null &&
          l.status !== "invalid" &&
          now - new Date(l.created_at).getTime() < 10 * 60 * 1000,
      );
      return scoring ? 4000 : false;
    },
    refetchIntervalInBackground: true,
  });
}
