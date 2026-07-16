"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { NotificationBell } from "@/components/notifications/notification-bell";
import { Button } from "@/components/ui/button";
import { clearToken, getToken } from "@/lib/auth";
import { useMe } from "@/lib/hooks/use-me";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "工作台" },
  { href: "/leads", label: "线索" },
  { href: "/discovery", label: "线索发现" },
  { href: "/accounts", label: "客户" },
  { href: "/opportunities", label: "商机" },
  { href: "/scripts", label: "话术" },
  { href: "/products", label: "产品库" },
  { href: "/product-advisor", label: "产品咨询" },
  { href: "/contracts", label: "合同" },
  { href: "/forecast", label: "预测" },
  { href: "/analytics", label: "业绩" },
  { href: "/assistant", label: "助手" },
];

// M15 售后中心：独立子系统（自带客户聊天页与管理控制台），新窗口打开
const AFTERSALES_URL = process.env.NEXT_PUBLIC_AFTERSALES_URL ?? "http://localhost:8100";

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const navItems = [
    ...NAV_ITEMS,
    ...(me?.role === "admin" ? [{ href: "/admin", label: "管理" }] : []),
  ];

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
    }
  }, [router, pathname]);

  function handleLogout() {
    clearToken();
    queryClient.clear(); // 清空上一账号的所有业务缓存，防止换号后泄漏
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b bg-background">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <span className="font-semibold">AI 销售助手</span>
          <nav className="flex flex-1 items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-muted",
                  pathname.startsWith(item.href)
                    ? "bg-muted font-medium"
                    : "text-muted-foreground",
                )}
              >
                {item.label}
              </Link>
            ))}
            <a
              href={`${AFTERSALES_URL}/admin`}
              target="_blank"
              rel="noreferrer"
              className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted"
              title="售后中心（独立子系统，新窗口打开）"
            >
              售后中心 ↗
            </a>
          </nav>
          <NotificationBell />
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            退出登录
          </Button>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4">{children}</div>
    </div>
  );
}
