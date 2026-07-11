"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ContactSection } from "@/components/accounts/contact-section";
import { type AccountProfile, ProfileCard } from "@/components/accounts/profile-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, apiErrorMessage } from "@/lib/api/client";

const TYPE_LABELS: Record<string, string> = {
  call: "电话",
  visit: "拜访",
  wechat: "微信",
  email: "邮件",
  meeting: "会议",
  other: "其他",
};

export default function AccountDetailPage() {
  const params = useParams<{ id: string }>();
  const accountId = params.id;
  const queryClient = useQueryClient();
  // 生成中状态：记录触发时的画像时间戳基线，轮询直到它变化
  const [pending, setPending] = useState<{ baseline: string | null } | null>(null);
  const generating = pending !== null;

  const { data: account } = useQuery({
    queryKey: ["account", accountId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/accounts/{account_id}", {
        params: { path: { account_id: accountId } },
      });
      if (error || !data) throw new Error("加载客户失败");
      return data;
    },
    refetchInterval: (query) => {
      if (!pending) return false;
      const updated = query.state.data?.ai_profile_updated_at ?? null;
      if (updated !== pending.baseline) {
        setPending(null);
        toast.success("AI 画像已生成");
        return false;
      }
      return 3000;
    },
  });

  const { data: timeline } = useQuery({
    queryKey: ["account-timeline", accountId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/accounts/{account_id}/timeline", {
        params: { path: { account_id: accountId } },
      });
      if (error || !data) throw new Error("加载时间线失败");
      return data;
    },
  });

  async function handleGenerate() {
    if (!account) return;
    const { error } = await api.POST("/api/v1/accounts/{account_id}/profile", {
      params: { path: { account_id: accountId } },
    });
    if (error) {
      toast.error(`画像任务提交失败：${apiErrorMessage(error)}`);
      return;
    }
    const baseline = account.ai_profile_updated_at ?? null;
    setPending({ baseline });
    queryClient.invalidateQueries({ queryKey: ["account", accountId] });
    // 60s 超时保护：仍未完成则提示并停止轮询
    setTimeout(() => {
      setPending((p) => {
        if (p && p.baseline === baseline) {
          toast.error("画像生成超时，可能是 AI 服务不可用，请稍后重试");
          return null;
        }
        return p;
      });
    }, 60_000);
  }

  if (!account) {
    return (
      <main className="flex flex-1 items-center justify-center">
        <p className="text-muted-foreground">加载中…</p>
      </main>
    );
  }

  const profile = (account.ai_profile as AccountProfile | null) ?? null;

  return (
    <main className="flex-1 space-y-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold">{account.name}</h1>
        <p className="text-sm text-muted-foreground">
          {[account.industry, account.size, account.region].filter(Boolean).join(" · ") ||
            "暂无基本信息"}
          {account.owner_name && ` · 负责人：${account.owner_name}`}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <ContactSection accountId={accountId} contacts={account.contacts} />

          <Card>
            <CardHeader>
              <CardTitle>跟进时间线（{timeline?.length ?? 0}）</CardTitle>
            </CardHeader>
            <CardContent>
              {!timeline || timeline.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  暂无跟进记录（线索期与商机的记录会自动聚合到这里）
                </p>
              ) : (
                <ol className="relative space-y-4 border-l pl-4">
                  {timeline.map((item) => (
                    <li key={item.id} className="text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {new Date(item.created_at).toLocaleString("zh-CN", {
                            month: "2-digit",
                            day: "2-digit",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </span>
                        <Badge variant="outline">{item.related_label}</Badge>
                        <Badge variant="secondary">{TYPE_LABELS[item.type] ?? item.type}</Badge>
                        <span className="text-xs text-muted-foreground">{item.owner_name}</span>
                      </div>
                      <p className="mt-1">{item.content}</p>
                      {item.next_action && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          下一步：{item.next_action}
                          {item.next_action_date && `（${item.next_action_date}）`}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>

        <ProfileCard
          profile={profile}
          updatedAt={account.ai_profile_updated_at}
          generating={generating}
          onGenerate={handleGenerate}
        />
      </div>
    </main>
  );
}
