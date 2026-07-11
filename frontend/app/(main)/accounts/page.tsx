"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { AccountFormDialog } from "@/components/accounts/account-form-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api/client";

export default function AccountsPage() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["accounts", page, search],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/accounts", {
        params: { query: { page, page_size: 20, ...(search ? { q: search } : {}) } },
      });
      if (error || !data) throw new Error("加载客户失败");
      return data;
    },
  });

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <main className="flex-1 space-y-4 py-8">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">客户</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q);
            setPage(1);
          }}
          className="flex gap-2"
        >
          <Input
            placeholder="按公司名搜索"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="w-48"
          />
          <Button type="submit" variant="outline">
            搜索
          </Button>
        </form>
        <AccountFormDialog />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>公司名称</TableHead>
              <TableHead>行业</TableHead>
              <TableHead>规模</TableHead>
              <TableHead>地区</TableHead>
              <TableHead>负责人</TableHead>
              <TableHead>AI 画像</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  加载中…
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                  暂无客户
                </TableCell>
              </TableRow>
            ) : (
              items.map((account) => (
                <TableRow key={account.id}>
                  <TableCell className="font-medium">
                    <Link href={`/accounts/${account.id}`} className="hover:underline">
                      {account.name}
                    </Link>
                  </TableCell>
                  <TableCell>{account.industry ?? "—"}</TableCell>
                  <TableCell>{account.size ?? "—"}</TableCell>
                  <TableCell>{account.region ?? "—"}</TableCell>
                  <TableCell>{account.owner_name ?? "—"}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {account.ai_profile_updated_at
                      ? new Date(account.ai_profile_updated_at).toLocaleDateString("zh-CN")
                      : "未生成"}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>共 {data?.total ?? 0} 个客户</span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span>
            {page} / {totalPages}
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
      </div>
    </main>
  );
}
