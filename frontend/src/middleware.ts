/**
 * Redirects unauthenticated visitors to /login.
 *
 * This only checks that a session cookie is present — it is a UX guard, not the
 * security boundary. Every /api route is enforced by the backend, which
 * validates the session properly and rejects expired or revoked ones.
 */
import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "liq_session";
const PUBLIC_PATHS = ["/login"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  if (!req.cookies.get(SESSION_COOKIE)) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    // Remember where they were headed so login can send them back.
    url.searchParams.set("next", pathname === "/" ? "/" : pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except API routes (enforced server-side), Next internals and
  // static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
