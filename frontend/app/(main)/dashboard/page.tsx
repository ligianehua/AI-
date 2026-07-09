"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { clearToken, getToken } from "@/lib/auth";

type Me = { email: string; name: string; role: string };

export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api.GET("/api/v1/auth/me").then(({ data, error }) => {
      if (error || !data) {
        clearToken();
        router.replace("/login");
        return;
      }
      setMe(data);
    });
  }, [router]);

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  if (!me) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground">加载中…</p>
      </main>
    );
  }

  return (
    <main className="flex-1 p-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">工作台</h1>
          <Button variant="outline" onClick={handleLogout}>
            退出登录
          </Button>
        </div>
        <p className="text-muted-foreground">
          欢迎，{me.name}（{me.email} · {me.role}）。线索、客户、商机等模块将在后续里程碑上线。
        </p>
      </div>
    </main>
  );
}
