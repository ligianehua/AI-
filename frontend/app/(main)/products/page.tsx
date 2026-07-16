"use client";

import { ProductPanel } from "@/components/products/product-panel";

export default function ProductsPage() {
  return (
    <main className="flex-1 space-y-4 py-8">
      <h1 className="text-2xl font-semibold">产品库</h1>
      <p className="text-sm text-muted-foreground">
        上传规格书自动抽取参数入库；自然语言搜产品、勾选对比参数、为停产型号一键找在售替代——
        让沉睡在文件夹里的规格书变成可检索的资产。
      </p>
      <ProductPanel />
    </main>
  );
}
