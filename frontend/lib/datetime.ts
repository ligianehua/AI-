/** 时间显示统一固定 Asia/Shanghai（PLAN §6：UTC 存储、按上海时区展示），不随浏览器时区漂移。 */
const TZ = "Asia/Shanghai";

export function formatDate(value: string | Date): string {
  return new Date(value).toLocaleDateString("zh-CN", { timeZone: TZ });
}

export function formatDateTime(value: string | Date): string {
  return new Date(value).toLocaleString("zh-CN", { timeZone: TZ });
}

export function formatShortDateTime(value: string | Date): string {
  return new Date(value).toLocaleString("zh-CN", {
    timeZone: TZ,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
