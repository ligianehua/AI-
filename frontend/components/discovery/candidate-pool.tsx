"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, apiErrorMessage } from "@/lib/api/client";

type CandidateStatus = "pending" | "claimed" | "ignored";

const STATUS_LABELS: Record<CandidateStatus, string> = {
  pending: "待处理",
  claimed: "已领取",
  ignored: "已忽略",
};

export function CandidatePool() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<CandidateStatus>("pending");
  const [page, setPage] = useState(1);

  const { data } = useQuery({
    queryKey: ["discovery-candidates", status, page],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/discovery/candidates", {
        params: { query: { status, page, page_size: 10 } },
      });
      if (error || !data) throw new Error("加载候选池失败");
      return data;
    },
    // 抓取任务异步落库：待处理列表轮询刷新
    refetchInterval: status === "pending" ? 8000 : false,
    refetchIntervalInBackground: true,
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["discovery-candidates"] });
  }

  async function handleClaim(id: string) {
    const { data, error } = await api.POST("/api/v1/discovery/candidates/{candidate_id}/claim", {
      params: { path: { candidate_id: id } },
    });
    if (error) {
      toast.error(`领取失败：${apiErrorMessage(error)}`);
      return;
    }
    const dupCount = data?.duplicate_warnings.length ?? 0;
    toast.success(
      dupCount > 0
        ? `已转为线索并触发 AI 评分（注意：${dupCount} 条疑似撞单提示，见线索详情）`
        : "已转为线索并触发 AI 评分",
    );
    refresh();
    queryClient.invalidateQueries({ queryKey: ["leads"] });
  }

  async function handleIgnore(id: string) {
    const { error } = await api.POST("/api/v1/discovery/candidates/{candidate_id}/ignore", {
      params: { path: { candidate_id: id } },
    });
    if (error) {
      toast.error(`操作失败：${apiErrorMessage(error)}`);
      return;
    }
    refresh();
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>候选池（{data?.total ?? 0}）</CardTitle>
        <div className="flex items-center gap-2">
          <Select
            value={status}
            onValueChange={(v) => {
              setStatus(v as CandidateStatus);
              setPage(1);
            }}
          >
            <SelectTrigger className="w-28" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={refresh}>
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {(data?.items ?? []).map((c) => (
          <div key={c.id} className="rounded-md border px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{c.name}</span>
              <Badge variant="secondary">
                {c.city} · {c.category}
              </Badge>
              {c.duplicate_hint && (
                <Badge variant="destructive" title={c.duplicate_hint}>
                  疑似撞单
                </Badge>
              )}
              {status === "pending" && (
                <div className="ml-auto flex items-center gap-1">
                  <Button size="sm" onClick={() => handleClaim(c.id)}>
                    领取为线索
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground"
                    onClick={() => handleIgnore(c.id)}
                  >
                    忽略
                  </Button>
                </div>
              )}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
              {c.address && <span>{c.address}</span>}
              {c.phone && <span>{c.phone}</span>}
              {c.website && (
                <a
                  href={c.website}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline"
                >
                  {c.website}
                </a>
              )}
            </div>
            {c.duplicate_hint && (
              <p className="mt-1 text-xs text-amber-600">{c.duplicate_hint}</p>
            )}
          </div>
        ))}
        {data?.items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {status === "pending"
              ? "候选池为空。在上方订阅里点「立即抓取」，几秒后刷新。"
              : "暂无记录。"}
          </p>
        )}
        {totalPages > 1 && (
          <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              上一页
            </Button>
            <span>
              {page}/{totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              下一页
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
