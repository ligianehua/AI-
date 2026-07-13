"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatDate } from "@/lib/datetime";
import { api } from "@/lib/api/client";

const TYPE_LABELS: Record<string, string> = {
  stale_no_followup: "无跟进",
  stage_stuck: "阶段停滞",
  next_action_due: "行动到期",
};

export function NotificationBell() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: count } = useQuery({
    queryKey: ["unread-count"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/notifications/unread-count");
      if (error || !data) throw new Error("加载失败");
      return data.unread;
    },
    refetchInterval: 60_000,
  });

  const { data: list } = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/notifications", {
        params: { query: { page: 1, page_size: 20 } },
      });
      if (error || !data) throw new Error("加载失败");
      return data;
    },
    enabled: open,
  });

  function refreshNotificationCaches() {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["unread-count"] });
    queryClient.invalidateQueries({ queryKey: ["dashboard-notifications"] }); // 工作台风险卡同步
  }

  async function markRead(id: string) {
    try {
      await api.POST("/api/v1/notifications/{notification_id}/read", {
        params: { path: { notification_id: id } },
      });
      refreshNotificationCaches();
    } catch {
      toast.error("网络异常，请重试");
    }
  }

  async function markAllRead() {
    try {
      await api.POST("/api/v1/notifications/read-all");
      refreshNotificationCaches();
    } catch {
      toast.error("网络异常，请重试");
    }
  }

  return (
    <>
      <Button variant="ghost" size="sm" className="relative" onClick={() => setOpen(true)}>
        提醒
        {(count ?? 0) > 0 && (
          <Badge variant="destructive" className="ml-1 h-5 min-w-5 px-1 text-xs">
            {count}
          </Badge>
        )}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              风险提醒
              <Button variant="ghost" size="sm" onClick={markAllRead}>
                全部已读
              </Button>
            </DialogTitle>
          </DialogHeader>
          <ul className="max-h-96 space-y-2 overflow-y-auto">
            {(list?.items ?? []).map((n) => (
              <li
                key={n.id}
                className={`rounded-md border px-3 py-2 text-sm ${n.read_at ? "opacity-50" : ""}`}
              >
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{TYPE_LABELS[n.type] ?? n.type}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {formatDate(n.created_at)}
                  </span>
                  {!n.read_at && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="ml-auto h-6 px-2 text-xs"
                      onClick={() => markRead(n.id)}
                    >
                      已读
                    </Button>
                  )}
                </div>
                <p className="mt-1 font-medium">{n.title}</p>
                {n.body && <p className="text-xs text-muted-foreground">{n.body}</p>}
              </li>
            ))}
            {list?.items.length === 0 && (
              <li className="py-8 text-center text-sm text-muted-foreground">暂无提醒</li>
            )}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}
