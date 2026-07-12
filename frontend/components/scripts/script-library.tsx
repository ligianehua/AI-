"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { api, apiErrorMessage } from "@/lib/api/client";
import { useMe } from "@/lib/hooks/use-me";
import { CATEGORY_LABELS, type ScriptCategory } from "@/lib/script-labels";

function NewScriptDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<ScriptCategory>("opening");
  const [scenario, setScenario] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/scripts", {
        body: { category, scenario, content, tags: [] },
      });
      if (error) {
        toast.error(`保存失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("话术已入库（后台生成向量索引）");
      setScenario("");
      setContent("");
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["scripts"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">新增话术</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新增话术</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>分类 *</Label>
              <Select value={category} onValueChange={(v) => setCategory(v as ScriptCategory)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="sc_scenario">场景标题 *</Label>
              <Input
                id="sc_scenario"
                required
                placeholder="如：客户嫌贵-价值拆解"
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
              />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="sc_content">话术内容 *</Label>
            <Textarea
              id="sc_content"
              required
              rows={5}
              value={content}
              onChange={(e) => setContent(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "保存中…" : "保存"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ScriptLibrary() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canManage = me?.role === "admin" || me?.role === "manager";
  const [category, setCategory] = useState<ScriptCategory | "all">("all");
  const [page, setPage] = useState(1);

  const { data } = useQuery({
    queryKey: ["scripts", category, page],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/scripts", {
        params: {
          query: {
            page,
            page_size: 10,
            ...(category !== "all" ? { category } : {}),
          },
        },
      });
      if (error || !data) throw new Error("加载话术库失败");
      return data;
    },
  });

  async function handleDelete(id: string) {
    const { error } = await api.DELETE("/api/v1/scripts/{script_id}", {
      params: { path: { script_id: id } },
    });
    if (error) {
      toast.error("删除失败");
      return;
    }
    toast.success("已删除");
    queryClient.invalidateQueries({ queryKey: ["scripts"] });
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>话术库（{data?.total ?? 0}）</CardTitle>
        <div className="flex items-center gap-2">
          <Select
            value={category}
            onValueChange={(v) => {
              setCategory(v as ScriptCategory | "all");
              setPage(1);
            }}
          >
            <SelectTrigger className="w-32" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部分类</SelectItem>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {canManage && <NewScriptDialog />}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {(data?.items ?? []).map((s) => (
          <div key={s.id} className="rounded-md border px-3 py-2 text-sm">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{CATEGORY_LABELS[s.category]}</Badge>
              <span className="font-medium">{s.scenario}</span>
              <span className="text-xs text-muted-foreground">被引用 {s.usage_count} 次</span>
              {!s.has_embedding && (
                <span className="text-xs text-amber-600">待嵌入（关键词可检索）</span>
              )}
              {canManage && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto h-6 px-2 text-xs text-muted-foreground"
                  onClick={() => handleDelete(s.id)}
                >
                  删除
                </Button>
              )}
            </div>
            <p className="mt-1 text-muted-foreground">{s.content}</p>
          </div>
        ))}
        {data?.items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            话术库为空。提示：上线前需由业务方灌入 ≥50 条真实优质话术（可运行
            scripts.seed_scripts 灌入 12 条演示话术）
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
