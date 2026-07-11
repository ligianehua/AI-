import createClient, { type Middleware } from "openapi-fetch";

import { getToken } from "@/lib/auth";
import type { paths } from "@/lib/api/schema";

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
};

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
});

api.use(authMiddleware);

/** 后端错误响应统一为 {code, message, detail}，从 error 对象里安全取中文提示。 */
export function apiErrorMessage(error: unknown, fallback = "请求失败，请稍后重试"): string {
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}
