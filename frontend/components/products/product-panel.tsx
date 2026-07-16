"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, apiErrorMessage } from "@/lib/api/client";
import { getToken } from "@/lib/auth";
import { useMe } from "@/lib/hooks/use-me";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const STATUS_LABELS: Record<string, string> = {
  active: "在售",
  eol: "停产",
  draft: "草稿",
};

interface ProductOut {
  id: string;
  model_no: string;
  name: string;
  brand: string | null;
  category: string | null;
  status: string;
  specs: Record<string, unknown>;
  description: string | null;
  has_embedding: boolean;
}

interface CompareResult {
  matrix: {
    products: { model_no: string; name: string; brand: string; status: string }[];
    rows: { param: string; values: string[] }[];
  };
  analysis: { summary: string; key_differences: string[]; recommendation: string } | null;
  analysis_note: string | null;
}

interface AlternativesResult {
  target: { model_no: string; status: string };
  alternatives: {
    id: string;
    model_no: string;
    name: string;
    status: string;
    similarity: number;
    spec_diffs: string[];
  }[];
}

export function ProductPanel() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const canManage = me?.role === "admin" || me?.role === "manager";
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [searchHits, setSearchHits] = useState<{ product: ProductOut; score: number }[] | null>(
    null,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [comparing, setComparing] = useState(false);
  const [alternatives, setAlternatives] = useState<AlternativesResult | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data } = useQuery({
    queryKey: ["products"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/products", {
        params: { query: { page: 1, page_size: 50 } },
      });
      if (error || !data) throw new Error("加载产品库失败");
      return data;
    },
    refetchInterval: 15000, // 规格书抽取是异步任务：轻量轮询
    refetchIntervalInBackground: true,
  });

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`${API_BASE_URL}/api/v1/products/upload-spec`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      const body = await resp.json().catch(() => null);
      if (!resp.ok) {
        toast.error(`上传失败：${body?.message ?? resp.status}`);
        return;
      }
      toast.success(String(body?.message ?? "已提交"));
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["products"] }), 5000);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleSearch() {
    if (!query.trim()) {
      setSearchHits(null);
      return;
    }
    const { data: hits, error } = await api.POST("/api/v1/products/search", {
      body: { query: query.trim(), top_k: 5 },
    });
    if (error) {
      toast.error(`搜索失败：${apiErrorMessage(error)}`);
      return;
    }
    setSearchHits(hits as unknown as { product: ProductOut; score: number }[]);
  }

  function toggleSelect(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 4 ? [...prev, id] : prev,
    );
  }

  async function handleCompare() {
    setComparing(true);
    setCompare(null);
    try {
      const { data: result, error } = await api.POST("/api/v1/products/compare", {
        body: { product_ids: selected },
      });
      if (error) {
        toast.error(`对比失败：${apiErrorMessage(error)}`);
        return;
      }
      setCompare(result as unknown as CompareResult);
    } finally {
      setComparing(false);
    }
  }

  async function handleAlternatives(id: string) {
    setAlternatives(null);
    const { data: result, error } = await api.GET("/api/v1/products/{product_id}/alternatives", {
      params: { path: { product_id: id } },
    });
    if (error) {
      toast.error(`查找替代失败：${apiErrorMessage(error)}`);
      return;
    }
    setAlternatives(result as unknown as AlternativesResult);
  }

  const items: { product: ProductOut; score?: number }[] =
    searchHits !== null
      ? searchHits.map((h) => ({ product: h.product, score: h.score }))
      : (data?.items ?? []).map((p) => ({ product: p as unknown as ProductOut }));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>
            产品（{searchHits !== null ? `搜索结果 ${items.length}` : (data?.total ?? 0)}）
          </CardTitle>
          <div className="flex items-center gap-2">
            {selected.length >= 2 && (
              <Button size="sm" disabled={comparing} onClick={handleCompare}>
                {comparing ? "对比中…" : `对比所选（${selected.length}）`}
              </Button>
            )}
            {canManage && (
              <>
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
                  {uploading ? "上传中…" : "上传规格书"}
                </Button>
              </>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSearch();
            }}
          >
            <Input
              placeholder="自然语言搜产品，如：380V 的变频器 / 载重一吨以上的 AGV"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (!e.target.value.trim()) setSearchHits(null);
              }}
            />
            <Button type="submit" variant="outline">
              搜索
            </Button>
          </form>

          {items.map(({ product: p, score }) => (
            <div key={p.id} className="rounded-md border px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(p.id)}
                  onChange={() => toggleSelect(p.id)}
                  title="勾选参与对比（2-4 个）"
                />
                <span className="font-medium">{p.model_no}</span>
                <span>{p.name}</span>
                {p.brand && <Badge variant="outline">{p.brand}</Badge>}
                {p.category && <Badge variant="outline">{p.category}</Badge>}
                <Badge variant={p.status === "eol" ? "destructive" : "secondary"}>
                  {STATUS_LABELS[p.status] ?? p.status}
                </Badge>
                {score !== undefined && (
                  <span className="text-xs text-muted-foreground">相关度 {score}</span>
                )}
                <div className="ml-auto flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
                  >
                    {expandedId === p.id ? "收起" : "参数"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => handleAlternatives(p.id)}>
                    找替代
                  </Button>
                </div>
              </div>
              {expandedId === p.id && (
                <div className="mt-2 grid gap-1 border-t pt-2 text-sm md:grid-cols-2">
                  {Object.entries(p.specs).map(([k, v]) => (
                    <p key={k}>
                      <span className="text-muted-foreground">{k}：</span>
                      {String(v)}
                    </p>
                  ))}
                  {p.description && (
                    <p className="text-muted-foreground md:col-span-2">{p.description}</p>
                  )}
                </div>
              )}
            </div>
          ))}
          {items.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {searchHits !== null
                ? "没有匹配的产品。"
                : "产品库为空。上传规格书或手动录入，让 AI 建档。"}
            </p>
          )}
        </CardContent>
      </Card>

      {compare && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>参数对比</CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setCompare(null)}>
              关闭
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b">
                    <th className="py-1 pr-4 text-left text-muted-foreground">参数</th>
                    {compare.matrix.products.map((p) => (
                      <th key={p.model_no} className="py-1 pr-4 text-left">
                        {p.model_no}
                        {p.status === "eol" && (
                          <Badge variant="destructive" className="ml-1">
                            停产
                          </Badge>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compare.matrix.rows.map((row) => {
                    const uniq = new Set(row.values.filter((v) => v !== "—"));
                    const differs = uniq.size > 1;
                    return (
                      <tr key={row.param} className="border-b last:border-0">
                        <td className="py-1 pr-4 text-muted-foreground">{row.param}</td>
                        {row.values.map((v, i) => (
                          <td key={i} className={`py-1 pr-4 ${differs ? "font-medium" : ""}`}>
                            {v}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {compare.analysis ? (
              <div className="space-y-2 text-sm">
                <p>{compare.analysis.summary}</p>
                <ul className="list-inside list-disc space-y-0.5">
                  {compare.analysis.key_differences.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
                <p className="text-muted-foreground">建议：{compare.analysis.recommendation}</p>
              </div>
            ) : (
              compare.analysis_note && (
                <p className="text-sm text-amber-600">{compare.analysis_note}</p>
              )
            )}
          </CardContent>
        </Card>
      )}

      {alternatives && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>
              {alternatives.target.model_no} 的替代推荐
              {alternatives.target.status === "eol" && "（已停产 → 仅推在售）"}
            </CardTitle>
            <Button variant="ghost" size="sm" onClick={() => setAlternatives(null)}>
              关闭
            </Button>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {alternatives.alternatives.map((a) => (
              <div key={a.id} className="rounded-md border px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{a.model_no}</span>
                  <span>{a.name}</span>
                  <Badge variant="secondary">相似度 {(a.similarity * 100).toFixed(1)}%</Badge>
                </div>
                {a.spec_diffs.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    参数差异：{a.spec_diffs.join("；")}
                  </p>
                )}
              </div>
            ))}
            {alternatives.alternatives.length === 0 && (
              <p className="text-muted-foreground">
                库内暂无合适的在售替代（可在产品详情放开「含停产」重查）。
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
