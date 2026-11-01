import { supabaseBrowser } from "./supabase";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const auth = supabaseBrowser();
  const { data } = await auth.auth.getSession();
  const headers = new Headers(init.headers);
  if (data.session?.access_token) headers.set("Authorization", `Bearer ${data.session.access_token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const info = await response.json().catch(() => ({}));
    throw new Error(info.detail || `The request failed (${response.status}).`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function jsonBody(value: unknown) { return JSON.stringify(value); }
export { API_URL };
