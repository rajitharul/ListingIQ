"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { CurrentUser } from "@/types";

export default function Header() {
  const [me, setMe] = useState<CurrentUser | null>(null);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  };

  const remainingPct = me?.daily_token_limit
    ? Math.round((me.tokens_remaining / me.daily_token_limit) * 100)
    : null;

  return (
    <header className="border-b border-[var(--card-border)] bg-white/90 backdrop-blur-lg sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-500 flex items-center justify-center">
            <span className="text-white font-bold text-lg">L</span>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">ListingIQ</h1>
            <p className="text-xs text-[var(--text-muted)]">
              Product Listing Optimization
            </p>
          </div>
        </Link>

        <div className="flex items-center gap-3">
          {me && remainingPct !== null && (
            <span
              className="text-xs text-[var(--text-muted)] hidden sm:inline"
              title={`${me.tokens_remaining.toLocaleString()} of ${me.daily_token_limit.toLocaleString()} tokens left today`}
            >
              {remainingPct}% budget left
            </span>
          )}

          {me?.role === "admin" && (
            <Link
              href="/admin"
              className="text-xs px-3 py-1.5 rounded-lg border border-[var(--card-border)] hover:bg-[var(--card-border)]/20"
            >
              Admin
            </Link>
          )}

          {me ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--text-muted)] hidden md:inline">
                {me.email}
              </span>
              <button
                onClick={logout}
                className="text-xs px-3 py-1.5 rounded-lg border border-[var(--card-border)] hover:bg-[var(--card-border)]/20"
              >
                Sign out
              </button>
            </div>
          ) : (
            <span className="text-xs px-3 py-1 rounded-full bg-[var(--accent)]/10 text-[var(--accent-light)] border border-[var(--accent)]/20">
              8-Agent Pipeline
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
