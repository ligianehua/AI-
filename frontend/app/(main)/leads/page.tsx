"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { AssignDialog } from "@/components/leads/assign-dialog";
import { ConvertDialog } from "@/components/leads/convert-dialog";
import { ImportDialog } from "@/components/leads/import-dialog";
import { LeadFormDialog } from "@/components/leads/lead-form-dialog";
import { ScoreDetailDialog } from "@/components/leads/score-detail-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, apiErrorMessage } from "@/lib/api/client";
import { useLeads, type LeadOut, type LeadStatus } from "@/lib/hooks/use-leads";
import { useMe } from "@/lib/hooks/use-me";
import { SOURCE_LABELS, STATUS_LABELS } from "@/lib/leads-labels";

function ScoreCell({ lead, onShowDetail }: { lead: LeadOut; onShowDetail: () => void }) {
  if (lead.score === null) {
    return lead.status === "invalid" ? (
      <span className="text-muted-foreground">—</span>
    ) : (
      <Badge variant="outline" className="animate-pulse">
        评分中…
      </Badge>
    );
  }
  const variant = lead.score >= 70 ? "default" : lead.score >= 40 ? "secondary" : "outline";
  return (
    <button onClick={onShowDetail} className="flex items-center gap-1" title="查看评分理由">
      <Badge variant={variant}>{lead.score}</Badge>
      <span className="text-xs text-muted-foreground">参考分</span>
    </button>
  );
}

export default function LeadsPage() {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<LeadStatus | "all">("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [detailLead, setDetailLead] = useState<LeadOut | null>(null);
  const [convertTarget, setConvertTarget] = useState<LeadOut | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);

  const { data, isLoading } = useLeads({ page, status, sort: "-score" });
  const canAssign = me?.role === "manager" || me?.role === "admin";
  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  async function handleRescore(lead: LeadOut) {
    const { error } = await api.POST("/api/v1/leads/{lead_id}/score", {
      params: { path: { lead_id: lead.id } },
    });
    if (error) {
      toast.error("评分任务提交失败");
      return;
    }
    toast.success("评分任务已提交，稍后自动刷新");
    queryClient.invalidateQueries({ queryKey: ["leads"] });
  }

  async function handleStatusChange(lead: LeadOut, newStatus: LeadStatus) {
    const { error } = await api.PATCH("/api/v1/leads/{lead_id}", {
      params: { path: { lead_id: lead.id } },
      body: { status: newStatus },
    });
    if (error) {
      toast.error(`状态修改失败：${apiErrorMessage(error)}`);
      return;
    }
    queryClient.invalidateQueries({ queryKey: ["leads"] });
  }

  function toggleSelect(id: string, checked: boolean) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  }

  return (
    <main className="flex-1 space-y-4 py-8">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-2xl font-semibold">线索</h1>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v as LeadStatus | "all");
            setPage(1);
          }}
        >
          <SelectTrigger className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {canAssign && (
          <Button
            variant="outline"
            disabled={selected.length === 0}
            onClick={() => setAssignOpen(true)}
          >
            分配（{selected.length}）
          </Button>
        )}
        <ImportDialog />
        <LeadFormDialog />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              {canAssign && <TableHead className="w-10" />}
              <TableHead>评分</TableHead>
              <TableHead>客户公司</TableHead>
              <TableHead>联系人</TableHead>
              <TableHead>手机号</TableHead>
              <TableHead>来源</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>负责人</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                  加载中…
                </TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                  暂无线索，点击「新建线索」或「Excel 导入」开始
                </TableCell>
              </TableRow>
            ) : (
              items.map((lead) => (
                <TableRow key={lead.id}>
                  {canAssign && (
                    <TableCell>
                      <Checkbox
                        checked={selected.includes(lead.id)}
                        onCheckedChange={(c) => toggleSelect(lead.id, c === true)}
                      />
                    </TableCell>
                  )}
                  <TableCell>
                    <ScoreCell lead={lead} onShowDetail={() => setDetailLead(lead)} />
                  </TableCell>
                  <TableCell className="max-w-48 truncate font-medium" title={lead.account_name}>
                    {lead.account_name}
                  </TableCell>
                  <TableCell>{lead.contact_name ?? "—"}</TableCell>
                  <TableCell>{lead.contact_phone ?? "—"}</TableCell>
                  <TableCell>{SOURCE_LABELS[lead.source]}</TableCell>
                  <TableCell>
                    {lead.status === "converted" ? (
                      <Badge>已转化</Badge>
                    ) : (
                      <Select
                        value={lead.status}
                        onValueChange={(v) => handleStatusChange(lead, v as LeadStatus)}
                      >
                        <SelectTrigger size="sm" className="h-7 w-24 text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(["new", "contacted", "qualified", "invalid"] as const).map((s) => (
                            <SelectItem key={s} value={s}>
                              {STATUS_LABELS[s]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </TableCell>
                  <TableCell>{lead.owner_name ?? "—"}</TableCell>
                  <TableCell className="space-x-1 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRescore(lead)}
                      disabled={lead.status === "invalid"}
                    >
                      重算
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={lead.status === "converted" || lead.status === "invalid"}
                      onClick={() => setConvertTarget(lead)}
                    >
                      转化
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>共 {data?.total ?? 0} 条</span>
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

      <ScoreDetailDialog lead={detailLead} onClose={() => setDetailLead(null)} />
      <ConvertDialog lead={convertTarget} onClose={() => setConvertTarget(null)} />
      <AssignDialog
        leadIds={selected}
        open={assignOpen}
        onClose={() => setAssignOpen(false)}
        onAssigned={() => setSelected([])}
      />
    </main>
  );
}
