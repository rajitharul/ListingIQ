"use client";

export default function Header() {
  return (
    <header className="border-b border-[var(--card-border)] bg-white/90 backdrop-blur-lg sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-500 flex items-center justify-center">
            <span className="text-white font-bold text-lg">L</span>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight">ListingIQ</h1>
            <p className="text-xs text-[var(--text-muted)]">
              Product Listing Optimization
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs px-3 py-1 rounded-full bg-[var(--accent)]/10 text-[var(--accent-light)] border border-[var(--accent)]/20">
            8-Agent Pipeline
          </span>
        </div>
      </div>
    </header>
  );
}
