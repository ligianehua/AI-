"use client";

import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type LeadImportReport = components["schemas"]["LeadImportReport"];

export async function importLeadsFile(file: File): Promise<LeadImportReport> {
  const formData = new FormData();
  formData.append("file", file);
  const { data, error } = await api.POST("/api/v1/leads/import", {
    // multipart：绕过默认 JSON 序列化，Content-Type 交给浏览器生成 boundary
    body: formData as unknown as { file: string },
    bodySerializer: (body: unknown) => body as FormData,
    headers: { "Content-Type": null },
  });
  if (error || !data) throw new Error("导入失败，请检查文件格式");
  return data;
}

export async function downloadImportTemplate(): Promise<void> {
  const { data, error } = await api.GET("/api/v1/leads/import-template", {
    parseAs: "blob",
  });
  if (error || !data) throw new Error("模板下载失败");
  const url = URL.createObjectURL(data as Blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "leads_import_template.xlsx";
  anchor.click();
  URL.revokeObjectURL(url);
}
