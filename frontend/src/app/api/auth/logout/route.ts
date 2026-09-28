/** Logout: ends the session server-side, then clears the cookie. */
import { cookies } from "next/headers";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";
const SESSION_COOKIE = "liq_session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(): Promise<Response> {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (session) {
    try {
      await fetch(`${BACKEND}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session}` },
        cache: "no-store",
      });
    } catch {
      // Backend unreachable: still clear the cookie so the browser logs out.
    }
  }
  const res = Response.json({ status: "logged_out" });
  res.headers.append(
    "Set-Cookie",
    `${SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`,
  );
  return res;
}
