type Method = "GET" | "POST" | "PUT" | "DELETE";

function getCsrfCookie(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: Method; body?: unknown; form?: FormData } = {},
): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = getCsrfCookie();

  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form; // don't set Content-Type; browser adds multipart boundary
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(path, {
    method, headers, body, credentials: "same-origin",
  });
  if (res.status === 401) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}
