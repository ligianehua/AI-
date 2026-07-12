"use client";

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
  { href: "/accounts", label: "客户" },
  { href: "/opportunities", label: "商机" },
  { href: "/scripts", label: "话术" },
];

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
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
