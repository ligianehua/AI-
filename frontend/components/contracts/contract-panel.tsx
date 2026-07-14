"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, apiErrorMessage } from "@/lib/api/client";
import { getToken } from "@/lib/auth";
import { formatShortDateTime } from "@/lib/datetime";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const STATUS_LABELS: Record<string, string> = {
  processing: "处理中",
  ready: "已完成",
  failed: "失败",
};

const LEVEL_LABELS: Record<string, string> = {
  high: "高风险",
  medium: "中风险",
  low: "低风险",
};

function GenerateDraftDialog() {
  const [open, setOpen] = useState(false);
  const [opportunityId, setOpportunityId] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("");
  const [generating, setGenerating] = useState(false);

  const { data: opps } = useQuery({
    queryKey: ["opps-options"],
    enabled: open,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/opportunities/kanban");
      if (error || !data) throw new Error("加载商机失败");
      // 看板按阶段分组 → 拍平成选项（won/lost 也保留，便于补签合同）
      return data.columns.flatMap((col) => col.items);
    },
  });

  async function handleGenerate() {
    if (!opportunityId) return;
    setGenerating(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/v1/contracts/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({
          opportunity_id: opportunityId,
          payment_terms: paymentTerms || null,
        }),
      });
      if (!resp.ok) {
        toast.error("生成失败，请稍后重试");
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const dispo = resp.headers.get("Content-Disposition") ?? "";
      const match = /filename\*=UTF-8''(.+)/.exec(dispo);
      a.download = match ? decodeURIComponent(match[1]) : "合同草稿.docx";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("草稿已下载（正式签署前须经法务审核）");
      setOpen(false);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          从商机生成草稿
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>生成标准合同草稿（docx）</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>商机 *</Label>
            <Select value={opportunityId} onValueChange={setOpportunityId}>
              <SelectTrigger>
                <SelectValue placeholder="选择商机" />
              </SelectTrigger>
              <SelectContent>
                {(opps ?? []).map((o) => (
                  <SelectItem key={o.id} value={o.id}>
                    {o.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ct_pay">付款方式（可选，留空用默认 5/5 分期）</Label>
            <Input
              id="ct_pay"
              placeholder="如：签署后一次性支付全款"
              value={paymentTerms}
              onChange={(e) => setPaymentTerms(e.target.value)}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            生成的是草稿：甲方与金额来自商机，乙方等信息需自行补全，正式签署前须经法务审核。
          </p>
          <Button onClick={handleGenerate} disabled={generating || !opportunityId}>
            {generating ? "生成中…" : "生成并下载"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ContractPanel() {
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["contracts"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/contracts", {
        params: { query: { page: 1, page_size: 50 } },
      });
      if (error || !data) throw new Error("加载合同失败");
      return data;
    },
    // 处理是异步任务：有处理中的合同时轮询
    refetchInterval: (q) =>
      q.state.data?.items.some((c) => c.status === "processing") ? 4000 : false,
    refetchIntervalInBackground: true,
  });

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`${API_BASE_URL}/api/v1/contracts/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        toast.error(`上传失败：${body?.message ?? resp.status}`);
        return;
      }
      toast.success("已上传，AI 正在抽取要素与审查风险…");
      queryClient.invalidateQueries({ queryKey: ["contracts"] });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleReprocess(id: string) {
    const { error } = await api.POST("/api/v1/contracts/{contract_id}/reprocess", {
      params: { path: { contract_id: id } },
    });
    if (error) {
      toast.error(`重试失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success("已重新提交处理");
    queryClient.invalidateQueries({ queryKey: ["contracts"] });
  }

  async function handleDelete(id: string) {
    const { error } = await api.DELETE("/api/v1/contracts/{contract_id}", {
      params: { path: { contract_id: id } },
    });
    if (error) {
      toast.error("删除失败");
      return;
    }
    toast.success("已删除");
    queryClient.invalidateQueries({ queryKey: ["contracts"] });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>合同（{data?.total ?? 0}）</CardTitle>
        <div className="flex items-center gap-2">
          <GenerateDraftDialog />
          <input
            ref={fileRef}
            type="file"
            accept=".txt,.md,.docx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUpload(f);
            }}
          />
          <Button size="sm" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? "上传中…" : "上传合同"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {(data?.items ?? []).map((c) => (
          <div key={c.id} className="rounded-md border px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{c.name}</span>
              <Badge
                variant={
                  c.status === "ready"
                    ? "secondary"
                    : c.status === "failed"
                      ? "destructive"
                      : "outline"
                }
              >
                {STATUS_LABELS[c.status] ?? c.status}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {c.owner_name} · {formatShortDateTime(c.created_at)}
              </span>
              <div className="ml-auto flex items-center gap-1">
                {c.status === "ready" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                  >
                    {expandedId === c.id ? "收起" : "查看结果"}
                  </Button>
                )}
                {c.status === "failed" && (
                  <Button variant="outline" size="sm" onClick={() => handleReprocess(c.id)}>
                    重试
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  onClick={() => handleDelete(c.id)}
                >
                  删除
                </Button>
              </div>
            </div>
            {c.status === "failed" && c.error_msg && (
              <p className="mt-1 text-xs text-destructive">{c.error_msg}</p>
            )}
            {expandedId === c.id && c.extracted && (
              <div className="mt-2 space-y-3 border-t pt-2">
                <div className="grid gap-1 text-sm md:grid-cols-2">
                  <p>甲方：{String(c.extracted.party_a ?? "—")}</p>
                  <p>乙方：{String(c.extracted.party_b ?? "—")}</p>
                  <p>金额：{String(c.extracted.amount ?? "—")}</p>
                  <p>期限：{String(c.extracted.period ?? "—")}</p>
                  <p>签署日期：{String(c.extracted.sign_date ?? "—")}</p>
                </div>
                {Array.isArray(c.extracted.payment_terms) &&
                  c.extracted.payment_terms.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground">付款约定</p>
                      <ul className="list-inside list-disc text-sm">
                        {(c.extracted.payment_terms as string[]).map((t, i) => (
                          <li key={i}>{t}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                {c.review && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-muted-foreground">风险审查</p>
                    {Array.isArray(c.review.risks) && c.review.risks.length > 0 ? (
                      (
                        c.review.risks as {
                          clause_quote: string;
                          level: string;
                          issue: string;
                          suggestion: string;
                        }[]
                      ).map((r, i) => (
                        <div key={i} className="rounded-md border bg-muted/30 px-2 py-1.5">
                          <div className="flex items-center gap-2">
                            <Badge variant={r.level === "high" ? "destructive" : "secondary"}>
                              {LEVEL_LABELS[r.level] ?? r.level}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              「{r.clause_quote}」
                            </span>
                          </div>
                          <p className="mt-1 text-sm">{r.issue}</p>
                          <p className="text-xs text-muted-foreground">建议：{r.suggestion}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">未发现明显风险条款</p>
                    )}
                    {Array.isArray(c.review.missing_clauses) &&
                      c.review.missing_clauses.length > 0 && (
                        <p className="text-sm text-amber-600">
                          缺失条款提示：{(c.review.missing_clauses as string[]).join("；")}
                        </p>
                      )}
                    {typeof c.review.overall_note === "string" && (
                      <p className="text-xs text-muted-foreground">{c.review.overall_note}</p>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {data?.items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            还没有合同。点「上传合同」做 AI 初筛，或「从商机生成草稿」。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
