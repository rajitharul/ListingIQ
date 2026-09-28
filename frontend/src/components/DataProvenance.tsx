"use client";

import { isLiveData, platformLabel, type CompetitorScoutResult } from "@/types";

/**
 * States where the competitor data came from.
 *
 * This is not decoration. Every score, gap and recommendation in the report is
 * derived from these competitors, so a buyer needs to know at a glance whether
 * they are looking at observed marketplace data or a model's estimate. Estimated
 * data gets a warning treatment, never the neutral or positive styling that
 * would let it pass for real.
 */

function relativeTime(iso?: string): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function DataProvenance({ data }: { data: CompetitorScoutResult }) {
  // Shared allowlist, not an inline denylist. The previous check treated any
  // unfamiliar data_source as live, so a new provider would have inherited the
  // green "observed data" pill without anyone deciding that it should.
  const isLive = isLiveData(data.data_source);
  const when = relativeTime(data.fetched_at);

  if (isLive) {
    // A competitive set can now span several storefronts, so one pill naming
    // one platform would be a claim about the data that is no longer true.
    const breakdown = Object.entries(data.platform_breakdown ?? {}).sort(
      (a, b) => b[1] - a[1],
    );
    const unread =
      (data.discovery_only_count ?? 0) + (data.failed_count ?? 0);

    return (
      <div className="flex flex-col gap-1.5 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-600/10 text-emerald-700 border border-emerald-600/20">
            <span aria-hidden="true">●</span>
            Live data &middot; {data.listings.length} competitor
            {data.listings.length === 1 ? "" : "s"}
          </span>
          {breakdown.map(([slug, count]) => (
            <span
              key={slug}
              className="px-2 py-1 rounded-full bg-[var(--card-border)]/60 text-[var(--text-muted)]"
            >
              {count} &times; {platformLabel(slug)}
            </span>
          ))}
          {when && (
            <span className="text-[var(--text-muted)]">
              fetched {when}
              {data.from_cache && " · cached"}
            </span>
          )}
        </div>
        {unread > 0 && (
          <p className="text-amber-700">
            {unread} of {data.listings.length} page
            {data.listings.length === 1 ? "" : "s"} could not be read in full &mdash;
            shown as competitors, but excluded from the benchmark so a failed
            read is not scored as a weak listing.
          </p>
        )}
        {data.provider_note && (
          <p className="text-[var(--text-muted)]">{data.provider_note}</p>
        )}
      </div>
    );
  }

  return (
    <div
      role="note"
      className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2"
    >
      <p className="text-xs font-semibold text-amber-700 flex items-center gap-1.5">
        <span aria-hidden="true">⚠</span>
        AI-estimated competitors — not live marketplace data
      </p>
      <p className="text-xs text-[var(--text-muted)] mt-1 leading-relaxed">
        These brands, prices, ratings and review counts are generated from model
        knowledge, not fetched from a live storefront. Treat the scores and gaps
        below as indicative rather than an audited benchmark.
        {data.provider_note ? ` (${data.provider_note})` : ""}
      </p>
    </div>
  );
}
