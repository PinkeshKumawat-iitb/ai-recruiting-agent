import { createBrowserClient } from "@supabase/ssr";
let client: ReturnType<typeof createBrowserClient> | null = null;
export function supabaseBrowser() {
  if (client) return client;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) throw new Error("Supabase is not configured yet. Copy .env.example to .env.local and add your project URL and publishable key.");
  client = createBrowserClient(url, key);
  return client;
}
