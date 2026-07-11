"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/** 镜像后端 app/ai/schemas.py 的 AccountProfileOutput（ai_profile 在 OpenAPI 中是自由 JSON）。 */
export interface AccountProfile {
  company_overview: string;
  pain_points: string[];
  decision_chain: { contact: string; role: string; attitude: string }[];
  cooperation_stage_analysis: string;
  risks: string[];
  suggestions: string[];
  confidence_note: string;
}

type Profile = AccountProfile;

export function ProfileCard({
  profile,
  updatedAt,
  generating,
  onGenerate,
}: {
  profile: Profile | null;
  updatedAt: string | null;
  generating: boolean;
  onGenerate: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          AI 画像
          {updatedAt && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              更新于 {new Date(updatedAt).toLocaleString("zh-CN")}
            </span>
          )}
        </CardTitle>
        <Button size="sm" onClick={onGenerate} disabled={generating}>
          {generating ? "生成中…（约 30 秒内）" : profile ? "刷新画像" : "生成画像"}
        </Button>
      </CardHeader>
      <CardContent>
        {!profile ? (
          <p className="text-sm text-muted-foreground">
            {generating ? "AI 正在阅读客户资料与跟进记录…" : "尚未生成画像，点击右上角按钮生成"}
          </p>
        ) : (
          <div className="space-y-4 text-sm">
            <section>
              <h4 className="mb-1 font-medium">公司概况</h4>
              <p className="text-muted-foreground">{profile.company_overview}</p>
            </section>
            {profile.pain_points.length > 0 && (
              <section>
                <h4 className="mb-1 font-medium">痛点</h4>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {profile.pain_points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </section>
            )}
            {profile.decision_chain.length > 0 && (
              <section>
                <h4 className="mb-1 font-medium">决策链</h4>
                <div className="space-y-1">
                  {profile.decision_chain.map((d) => (
                    <div key={d.contact} className="flex items-center gap-2">
                      <Badge variant="secondary">{d.contact}</Badge>
                      <span className="text-muted-foreground">
                        {d.role} · {d.attitude}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}
            <section>
              <h4 className="mb-1 font-medium">合作阶段</h4>
              <p className="text-muted-foreground">{profile.cooperation_stage_analysis}</p>
            </section>
            {profile.risks.length > 0 && (
              <section>
                <h4 className="mb-1 font-medium text-destructive">风险</h4>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {profile.risks.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </section>
            )}
            <section>
              <h4 className="mb-1 font-medium">行动建议</h4>
              <ul className="list-disc pl-5 text-muted-foreground">
                {profile.suggestions.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </section>
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              {profile.confidence_note}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
