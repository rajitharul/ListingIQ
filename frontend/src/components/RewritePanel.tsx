"use client";

import { useState } from "react";
import type { RewriteResult, ListingRewrite } from "@/types";

interface Props {
  rewrites: RewriteResult;
  originalTitle: string;
  originalBullets: string[];
  originalDescription: string;
}

function getScoreColor(score: number): string {
  if (score >= 7.5) return "var(--score-high)";
  if (score >= 5.0) return "var(--score-mid)";
  return "var(--score-low)";
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={handleCopy}
      className="text-[10px] px-2 py-1 rounded bg-[var(--card-border)] hover:bg-[var(--accent)] hover:text-white transition-colors"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function VariantCard({
  variant,
  originalScore,
}: {
  variant: ListingRewrite;
  originalScore: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const fullText = [
    variant.title,
    "",
    ...variant.bullet_points.map((b) => `• ${b}`),
    "",
    variant.description,
  ].join("\n");

  return (
    <div className="bg-[var(--background)] border border-[var(--card-border)] rounded-xl p-5 hover:border-[var(--accent)]/30 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold">{variant.variant_name}</h3>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
            Strategy: {variant.strategy}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right">
            <div
              className="text-lg font-black"
              style={{ color: getScoreColor(variant.expected_score) }}
            >
              {variant.expected_score.toFixed(1)}
            </div>
            <div className="text-[10px] text-[var(--text-muted)]">
              from {originalScore.toFixed(1)}
            </div>
          </div>
          <CopyButton text={fullText} />
        </div>
      </div>

      {/* Key changes */}
      <div className="flex flex-wrap gap-1 mb-3">
        {variant.key_changes.map((change, i) => (
          <span
            key={i}
            className="text-[10px] px-2 py-0.5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)]"
          >
            {change}
          </span>
        ))}
      </div>

      {/* Title */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase">
            Title
          </span>
          <CopyButton text={variant.title} />
        </div>
        <p className="text-sm font-medium bg-white rounded-lg p-2 border border-[var(--card-border)]/50">
          {variant.title}
        </p>
      </div>

      {/* Bullet Points */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase">
            Bullet Points
          </span>
          <CopyButton text={variant.bullet_points.map((b) => `• ${b}`).join("\n")} />
        </div>
        <div className="bg-white rounded-lg p-2 border border-[var(--card-border)]/50 space-y-1">
          {variant.bullet_points.map((bp, i) => (
            <p key={i} className="text-xs text-[var(--foreground)]">
              &bull; {bp}
            </p>
          ))}
        </div>
      </div>

      {/* Description (collapsible) */}
      <div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] font-semibold text-[var(--text-muted)] uppercase hover:text-[var(--accent)] transition-colors flex items-center gap-1"
        >
          Description
          <svg
            className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {expanded && (
          <div className="mt-1">
            <div className="flex justify-end mb-1">
              <CopyButton text={variant.description} />
            </div>
            <p className="text-xs text-[var(--foreground)]/80 bg-white rounded-lg p-2 border border-[var(--card-border)]/50">
              {variant.description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function RewritePanel({
  rewrites,
  originalTitle,
  originalBullets,
  originalDescription,
}: Props) {
  return (
    <div className="glass-card p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Optimized Rewrites</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            {rewrites.variants.length} variants generated &middot; Best score:{" "}
            <span className="font-bold" style={{ color: getScoreColor(rewrites.best_variant_score) }}>
              {rewrites.best_variant_score.toFixed(1)}
            </span>{" "}
            (from {rewrites.original_score.toFixed(1)})
          </p>
        </div>
      </div>

      {/* Original listing for comparison */}
      <details className="mb-6">
        <summary className="text-xs text-[var(--text-muted)] cursor-pointer hover:text-[var(--accent)]">
          Show original listing for comparison
        </summary>
        <div className="mt-2 bg-[var(--background)] rounded-lg p-4 border border-[var(--card-border)]">
          <p className="text-sm font-medium mb-2">{originalTitle}</p>
          <div className="space-y-1 mb-2">
            {originalBullets.map((bp, i) => (
              <p key={i} className="text-xs text-[var(--text-muted)]">&bull; {bp}</p>
            ))}
          </div>
          {originalDescription && (
            <p className="text-xs text-[var(--text-muted)]">{originalDescription}</p>
          )}
        </div>
      </details>

      <div className="space-y-4">
        {rewrites.variants.map((variant, i) => (
          <VariantCard
            key={i}
            variant={variant}
            originalScore={rewrites.original_score}
          />
        ))}
      </div>
    </div>
  );
}
