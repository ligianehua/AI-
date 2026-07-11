"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  downloadImportTemplate,
  importLeadsFile,
  type LeadImportReport,
} from "@/lib/api/leads";

export function ImportDialog() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState<LeadImportReport | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      toast.error("请先选择 Excel 文件");
      return;
    }
    setUploading(true);
    try {
      const result = await importLeadsFile(file);
      setReport(result);
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      toast.success(`导入完成：成功 ${result.imported} 条，失败 ${result.failed} 条`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导入失败");
    } finally {
      setUploading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) setReport(null);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline">Excel 导入</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Excel 批量导入</DialogTitle>
          <DialogDescription>
            按模板填写后上传（.xlsx），导入后自动触发 AI 评分
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Button
            variant="link"
            className="h-auto p-0"
            onClick={() => downloadImportTemplate().catch(() => toast.error("模板下载失败"))}
          >
            下载导入模板
          </Button>
          <div className="flex gap-2">
            <Input ref={fileRef} type="file" accept=".xlsx" />
            <Button onClick={handleUpload} disabled={uploading}>
              {uploading ? "导入中…" : "上传导入"}
            </Button>
          </div>
          {report && (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <p>
                共 {report.total_rows} 行：导入 <b>{report.imported}</b> 条，失败{" "}
                <b>{report.failed}</b> 条
              </p>
              {report.errors.length > 0 && (
                <div>
                  <p className="font-medium text-destructive">错误行：</p>
                  <ul className="max-h-32 overflow-y-auto text-muted-foreground">
                    {report.errors.map((e) => (
                      <li key={e.row}>
                        第 {e.row} 行：{e.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {report.duplicate_warnings.length > 0 && (
                <div>
                  <p className="font-medium text-amber-600">疑似撞单（已导入，请人工裁决）：</p>
                  <ul className="max-h-32 overflow-y-auto text-muted-foreground">
                    {report.duplicate_warnings.map((w) => (
                      <li key={w.row}>
                        第 {w.row} 行：{w.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
