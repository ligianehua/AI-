"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Me = components["schemas"]["UserOut"];

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me> => {
      const { data, error } = await api.GET("/api/v1/auth/me");
      if (error || !data) throw new Error("未登录");
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
}
