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
import { api, apiErrorMessage } from "@/lib/api/client";
import { formatShortDateTime } from "@/lib/datetime";

// 东南亚常用目标市场（值为英文，直接拼进 Places 查询）
const SEA_COUNTRIES: { value: string; label: string }[] = [
  { value: "Indonesia", label: "印度尼西亚" },
  { value: "Vietnam", label: "越南" },
  { value: "Thailand", label: "泰国" },
  { value: "Malaysia", label: "马来西亚" },
  { value: "Singapore", label: "新加坡" },
  { value: "Philippines", label: "菲律宾" },
];

function NewSubscriptionDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [country, setCountry] = useState("Indonesia");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");
  const [keyword, setKeyword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const { error } = await api.POST("/api/v1/discovery/subscriptions", {
        body: {
          country,
          city: city.trim(),
          category: category.trim(),
          keyword: keyword.trim() || null,
        },
      });
      if (error) {
        toast.error(`创建失败：${apiErrorMessage(error)}`);
        return;
      }
      toast.success("订阅已创建，点「立即抓取」拉取商户");
      setCity("");
      setCategory("");
      setKeyword("");
      setOpen(false);
      queryClient.invalidateQueries({ queryKey: ["discovery-subscriptions"] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">新建订阅</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建抓取订阅</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>国家 *</Label>
              <Select value={country} onValueChange={setCountry}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEA_COUNTRIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ds_city">城市 *（英文）</Label>
              <Input
                id="ds_city"
                required
                placeholder="如 Jakarta / Bangkok"
                value={city}
                onChange={(e) => setCity(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="ds_category">品类 *（英文）</Label>
              <Input
                id="ds_category"
                required
                placeholder="如 manufacturing / restaurant"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="ds_keyword">补充关键词（可选）</Label>
              <Input
                id="ds_keyword"
                placeholder="如 metal / halal"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
          </div>
          <Button type="submit" disabled={submitting}>
            {submitting ? "创建中…" : "创建"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SubscriptionPanel() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["discovery-subscriptions"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/discovery/subscriptions", {
        params: { query: { page: 1, page_size: 50 } },
      });
      if (error || !data) throw new Error("加载订阅失败");
      return data;
    },
  });

  async function handleRun(id: string) {
    const { data, error } = await api.POST("/api/v1/discovery/subscriptions/{sub_id}/run", {
      params: { path: { sub_id: id } },
    });
    if (error) {
      toast.error(`抓取失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success(data?.message ?? "抓取任务已提交");
    // 任务异步执行，稍后刷新订阅统计与候选池
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["discovery-subscriptions"] });
      queryClient.invalidateQueries({ queryKey: ["discovery-candidates"] });
    }, 4000);
  }

  async function handleToggle(id: string, isActive: boolean) {
    const { error } = await api.PATCH("/api/v1/discovery/subscriptions/{sub_id}", {
      params: { path: { sub_id: id } },
      body: { is_active: !isActive },
    });
    if (error) {
      toast.error(`操作失败：${apiErrorMessage(error)}`);
      return;
    }
    queryClient.invalidateQueries({ queryKey: ["discovery-subscriptions"] });
  }

  async function handleDelete(id: string) {
    const { error } = await api.DELETE("/api/v1/discovery/subscriptions/{sub_id}", {
      params: { path: { sub_id: id } },
    });
    if (error) {
      toast.error(`删除失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success("订阅已删除（候选池保留）");
    queryClient.invalidateQueries({ queryKey: ["discovery-subscriptions"] });
  }

  const countryLabel = (value: string) =>
    SEA_COUNTRIES.find((c) => c.value === value)?.label ?? value;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>抓取订阅（{data?.total ?? 0}）</CardTitle>
        <NewSubscriptionDialog />
      </CardHeader>
      <CardContent className="space-y-2">
        {(data?.items ?? []).map((s) => (
          <div
            key={s.id}
            className="flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <span className="font-medium">{s.name}</span>
            <Badge variant="secondary">
              {countryLabel(s.country)} · {s.city}
            </Badge>
            <Badge variant="outline">{s.category}</Badge>
            {s.keyword && <Badge variant="outline">{s.keyword}</Badge>}
            {!s.is_active && <Badge variant="destructive">已停用</Badge>}
            <span className="text-xs text-muted-foreground">
              {s.last_run_at
                ? `上次抓取 ${formatShortDateTime(s.last_run_at)}，新增 ${s.last_run_new ?? 0} 条`
                : "尚未抓取"}
            </span>
            <div className="ml-auto flex items-center gap-1">
              <Button size="sm" disabled={!s.is_active} onClick={() => handleRun(s.id)}>
                立即抓取
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleToggle(s.id, s.is_active)}>
                {s.is_active ? "停用" : "启用"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground"
                onClick={() => handleDelete(s.id)}
              >
                删除
              </Button>
            </div>
          </div>
        ))}
        {data?.items.length === 0 && (
          <p className="py-6 text-center text-sm text-muted-foreground">
            还没有订阅。点「新建订阅」选择目标市场开始找线索。
          </p>
        )}
      </CardContent>
    </Card>
  );
}
