"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/datetime";
import { api } from "@/lib/api/client";
import { useMe } from "@/lib/hooks/use-me";

const STATUS_LABELS: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  processing: { label: "处理中", variant: "secondary" },
  ready: { label: "已就绪", variant: "default" },
  failed: { label: "失败", variant: "destructive" },
};

export function KnowledgePanel() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canManage = me?.role === "admin" || me?.role === "manager";
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const { data } = useQuery({
    queryKey: ["knowledge-docs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/knowledge/docs", {
        params: { query: { page: 1, page_size: 20 } },
      });
      if (error || !data) throw new Error("加载知识库失败");
      return data;
    },
    // 有处理中的文档时轮询（后台标签页也继续，保证状态收敛）
    refetchInterval: (query) =>
      query.state.data?.items.some((d) => d.status === "processing") ? 3000 : false,
    refetchIntervalInBackground: true,
  });

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      toast.error("请选择文件（txt/md/docx）");
      return;
    }
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
      const token = getToken();
      const resp = await fetch(`${baseUrl}/api/v1/knowledge/docs`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => null);
        toast.error(`上传失败：${body?.message ?? resp.status}`);
        return;
      }
      toast.success("已上传，后台分块与嵌入处理中…");
      if (fileRef.current) fileRef.current.value = "";
      queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] });
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id: string) {
    const { error } = await api.DELETE("/api/v1/knowledge/docs/{doc_id}", {
      params: { path: { doc_id: id } },
    });
    if (error) {
      toast.error("删除失败");
      return;
    }
    queryClient.invalidateQueries({ queryKey: ["knowledge-docs"] });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>知识库（产品资料 / FAQ / 案例）</CardTitle>
        {canManage && (
          <div className="flex gap-2">
            <Input ref={fileRef} type="file" accept=".txt,.md,.docx" className="w-56" />
            <Button size="sm" onClick={handleUpload} disabled={uploading}>
              {uploading ? "上传中…" : "上传"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        {(data?.items ?? []).map((doc) => {
          const status = STATUS_LABELS[doc.status] ?? STATUS_LABELS.processing;
          return (
            <div key={doc.id} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
              <span className="font-medium">{doc.title}</span>
              <Badge variant={status.variant}>{status.label}</Badge>
              <span className="text-xs text-muted-foreground">{doc.chunk_count} 块</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {formatDate(doc.created_at)}
              </span>
              {canManage && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs text-muted-foreground"
                  onClick={() => handleDelete(doc.id)}
                >
                  删除
                </Button>
              )}
            </div>
          );
        })}
        {data?.items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            暂无知识文档，上传产品资料后推荐生成会自动引用
          </p>
        )}
      </CardContent>
    </Card>
  );
}
