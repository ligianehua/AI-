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
