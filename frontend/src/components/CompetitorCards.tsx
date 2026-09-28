"use client";

import { useState } from "react";
import DataProvenance from "@/components/DataProvenance";
import { platformLabel, type CompetitorScoutResult, type CompetitorListing } from "@/types";

interface Props {
  data: CompetitorScoutResult;
}

function renderStars(rating: number) {
  const full = Math.floor(rating);
  const half = rating - full >= 0.5;
  const stars: string[] = [];
  for (let i = 0; i < full; i++) stars.push("\u2605");
  if (half) stars.push("\u00BD");
  return stars.join("");
}

export default function CompetitorCards({ data }: Props) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? data.listings : data.listings.slice(0, 6);

  return (
    <div className="glass-card p-8">
      <div className="flex items-start justify-between mb-6 gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">Competitive Landscape</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1 mb-2">
            {data.listings.length} competitor listings &middot; benchmarked for {platformLabel(data.platform)}
          </p>
          <DataProvenance data={data} />
        </div>
        {data.listings.length > 6 && (
          <button
            onClick={() => setShowAll(!showAll)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            {showAll ? "Show less" : `Show all ${data.listings.length}`}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map((comp) => (
          <div
            key={comp.rank}
            className="bg-[var(--background)] border border-[var(--card-border)] rounded-xl p-5 hover:border-[var(--accent)]/30 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-[var(--text-muted)] bg-[var(--card-border)] rounded-full w-6 h-6 flex items-center justify-center">
                  {comp.rank}
                </span>
                <span className="text-xs font-semibold text-[var(--accent)]">
                  {comp.brand_name}
                </span>
              </div>
              {comp.price ? (
                <span className="text-sm font-bold">{comp.price}</span>
              ) : (
                <span className="text-[10px] text-[var(--text-muted)]">no price shown</span>
              )}
            </div>

            {comp.url ? (
              <a
                href={comp.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-sm font-medium line-clamp-2 mb-2 hover:text-[var(--accent)] transition-colors"
                title="Open this competitor's listing"
              >
                {comp.title}
              </a>
            ) : (
              <h3 className="text-sm font-medium line-clamp-2 mb-2">{comp.title}</h3>
            )}

            {/* Where this competitor was found. A set can span storefronts now,
                so the platform belongs on the card, not just in the header. */}
            <div className="flex flex-wrap items-center gap-1.5 mb-2">
              {comp.platform && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--card-border)]/60 text-[var(--text-muted)]">
                  {platformLabel(comp.platform)}
                </span>
              )}
              {comp.domain && comp.domain !== comp.platform && (
                <span className="text-[10px] text-[var(--text-muted)]">{comp.domain}</span>
              )}
              {comp.counts_toward_benchmark === false && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700"
                  title={comp.extraction_note || "This page could not be read in full"}
                >
                  not scored
                </span>
              )}
            </div>

            {/* A rating we never saw is not a rating of zero. Web-discovered
                competitors carry no rating at all, and rendering 0.0 stars
                would present an absence of data as a fact about the seller. */}
            {comp.rating > 0 ? (
              <div className="flex items-center gap-2 mb-3">
                <span className="text-amber-500 text-xs">{renderStars(comp.rating)}</span>
                <span className="text-xs font-medium">{comp.rating.toFixed(1)}</span>
                {comp.review_count > 0 && (
                  <span className="text-[10px] text-[var(--text-muted)]">
                    ({comp.review_count.toLocaleString()} reviews)
                  </span>
                )}
              </div>
            ) : (
              <div className="mb-3 text-[10px] text-[var(--text-muted)]">
                no published rating
              </div>
            )}

            {comp.badges.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {comp.badges.map((badge, i) => (
                  <span
                    key={i}
                    className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            )}

            {comp.bullet_points.length > 0 && (
              <div className="space-y-1">
                {comp.bullet_points.slice(0, 2).map((bp, i) => (
                  <p key={i} className="text-[10px] text-[var(--text-muted)] line-clamp-1">
                    &bull; {bp}
                  </p>
                ))}
                {comp.bullet_points.length > 2 && (
                  <p className="text-[10px] text-[var(--text-muted)] opacity-60">
                    +{comp.bullet_points.length - 2} more bullets
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
