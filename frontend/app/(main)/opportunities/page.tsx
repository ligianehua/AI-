"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { NewOpportunityDialog } from "@/components/opportunities/new-opportunity-dialog";
import { OpportunityDetailDialog } from "@/components/opportunities/opportunity-detail-dialog";
import {
  StageCloseDialog,
  type StageCloseTarget,
} from "@/components/opportunities/stage-close-dialog";
import { Badge } from "@/components/ui/badge";
import { api, apiErrorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import {
  formatWan,
  STAGE_LABELS,
  STAGE_ORDER,
  type KanbanColumn,
  type OpportunityOut,
  type OpportunityStage,
} from "@/lib/opportunity-labels";

function KanbanCard({
  opp,
  onClick,
}: {
  opp: OpportunityOut;
  onClick: () => void;
}) {
  return (
    <button
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", opp.id)}
      onClick={onClick}
      className="w-full cursor-grab rounded-md border bg-background p-2.5 text-left text-sm shadow-xs transition-shadow hover:shadow-md active:cursor-grabbing"
    >
      <p className="truncate font-medium" title={opp.name}>
        {opp.name}
      </p>
      <p className="truncate text-xs text-muted-foreground">{opp.account_name}</p>
      <div className="mt-1.5 flex items-center gap-1.5">
        <span className="text-xs font-semibold">{formatWan(Number(opp.amount))}</span>
        <span className="text-xs text-muted-foreground">{opp.probability}%</span>
        {opp.stuck_days > 7 && opp.stage !== "won" && opp.stage !== "lost" && (
          <Badge variant="destructive" className="ml-auto h-4 px-1 text-[10px]">
            {opp.stuck_days}天
          </Badge>
        )}
        <span className="ml-auto text-[10px] text-muted-foreground first:ml-0">
          {opp.owner_name}
        </span>
      </div>
    </button>
  );
}

export default function OpportunitiesPage() {
  const queryClient = useQueryClient();
  const [detail, setDetail] = useState<OpportunityOut | null>(null);
  const [closeTarget, setCloseTarget] = useState<StageCloseTarget | null>(null);
  const [dragOver, setDragOver] = useState<OpportunityStage | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["kanban"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/opportunities/kanban");
      if (error || !data) throw new Error("加载看板失败");
      return data;
    },
  });

  const columns: KanbanColumn[] = data?.columns ?? [];
  const byStage = new Map(columns.map((c) => [c.stage, c]));
  const allItems = columns.flatMap((c) => c.items);

  async function moveStage(oppId: string, stage: OpportunityStage) {
    const opp = allItems.find((o) => o.id === oppId);
    if (!opp || opp.stage === stage) return;
    if (stage === "won" || stage === "lost") {
      setCloseTarget({ opportunity: opp, stage });
      return;
    }
    const { error } = await api.PATCH("/api/v1/opportunities/{opportunity_id}/stage", {
      params: { path: { opportunity_id: oppId } },
      body: { stage },
    });
    if (error) {
      toast.error(`换阶段失败：${apiErrorMessage(error)}`);
      return;
    }
    toast.success(`已移至「${STAGE_LABELS[stage]}」`);
    queryClient.invalidateQueries({ queryKey: ["kanban"] });
  }

  return (
    <main className="flex-1 space-y-4 py-8">
      <div className="flex items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">商机看板</h1>
        <NewOpportunityDialog />
      </div>

      {isLoading ? (
        <p className="py-16 text-center text-muted-foreground">加载中…</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {STAGE_ORDER.map((stage) => {
            const col = byStage.get(stage);
            const items = col?.items ?? [];
            return (
              <div
                key={stage}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(stage);
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(null);
                  moveStage(e.dataTransfer.getData("text/plain"), stage);
                }}
                className={cn(
                  "flex min-h-64 flex-col rounded-lg border bg-muted/30 p-2 transition-colors",
                  dragOver === stage && "border-primary bg-primary/5",
                )}
              >
                <div className="mb-2 px-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{STAGE_LABELS[stage]}</span>
                    <Badge variant="secondary" className="h-5 px-1.5 text-xs">
                      {items.length}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {formatWan(col?.total_amount ?? 0)}
                    {stage !== "won" && stage !== "lost" && (
                      <span> · 加权 {formatWan(col?.weighted_amount ?? 0)}</span>
                    )}
                  </p>
                </div>
                <div className="flex flex-1 flex-col gap-2">
                  {items.map((opp) => (
                    <KanbanCard key={opp.id} opp={opp} onClick={() => setDetail(opp)} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <OpportunityDetailDialog opportunity={detail} onClose={() => setDetail(null)} />
      <StageCloseDialog target={closeTarget} onClose={() => setCloseTarget(null)} />
    </main>
  );
}
