"use client";

import { useState } from "react";
import {
  platformLabel,
  type CompetitorBenchmark,
  type ListingScore,
} from "@/types";

/**
 * The measured benchmark, finally on screen.
 *
 * Every competitor is scored on the same rubric as the user's listing, and the
 * averages are arithmetic over those scores. That work existed before this
 * component did — it was computed, cached and returned in the API response, but
 * nothing rendered it, so the customer saw a percentile with no way to check it.
 *
 * Two cohorts are shown because pooling them would not be honest: a 200-character
 * keyword-stacked marketplace title and a brand site's 40-character product name
 * are good listings by different rules. "Top 18% of Amazon sellers, top 31% of
 * the category" says something neither number says alone.
 */

interface Props {
  primary: CompetitorBenchmark;
  wide?: CompetitorBenchmark;
  scores: ListingScore;
}

function scoreColor(score: number): string {
  if (score >= 7.5) return "var(--score-high)";
  if (score >= 5.0) return "var(--score-mid)";
  return "var(--score-low)";
}

function ordinal(pct: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = pct % 100;
  return pct + (s[(v - 20) % 10] || s[v] || s[0]);
}

function CohortCard({
  label,
  benchmark,
  percentile,
  userScore,
  emphasis,
}: {
  label: string;
  benchmark: CompetitorBenchmark;
  percentile: number;
  userScore: number;
  emphasis: boolean;
}) {
  const n = benchmark.competitors.length;
  if (!n) return null;

  return (
    <div
      className={`rounded-xl p-4 border ${
        emphasis
          ? "border-[var(--accent)]/40 bg-[var(--accent)]/5"
          : "border-[var(--card-border)] bg-[var(--background)]"
      }`}
    >
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <h3 className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">
          {label}
        </h3>
        {emphasis && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--accent)] text-white">
            headline
          </span>
        )}
      </div>

      <p className="text-2xl font-black" style={{ color: scoreColor(userScore) }}>
        {ordinal(percentile)}
        <span className="text-sm font-medium text-[var(--text-muted)]">
          {" "}
          percentile
        </span>
      </p>

      <p className="text-xs text-[var(--text-muted)] mt-1">
        Your {userScore.toFixed(1)} against {n} competitor{n === 1 ? "" : "s"},
        averaging <strong>{benchmark.overall_mean.toFixed(1)}</strong>
      </p>

      {benchmark.platforms && benchmark.platforms.length > 0 && (
        <p className="text-[10px] text-[var(--text-muted)] mt-1">
          {benchmark.platforms.map(platformLabel).join(" · ")}
        </p>
      )}
    </div>
  );
}

export default function BenchmarkPanel({ primary, wide, scores }: Props) {
  const [open, setOpen] = useState(false);
  if (!primary.competitors.length) return null;

  const samePlatformIsHeadline = scores.percentile_basis !== "all_competitors";
  const showBoth =
    !!wide && wide.competitors.length !== primary.competitors.length;

  // A dimension measured on very few competitors is an anecdote, not a
  // benchmark. n already travels with each stat, so say so rather than
  // presenting every mean with equal confidence.
  const thin = primary.dimensions.filter((d) => d.n > 0 && d.n < 3);

  return (
    <div className="glass-card p-8">
      <div className="mb-5">
        <h2 className="text-lg font-semibold">Measured Benchmark</h2>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Every competitor was scored on the same rubric as your listing. These
          averages are arithmetic over those scores &mdash; not an estimate.
        </p>
      </div>

      <div className={`grid gap-3 ${showBoth ? "sm:grid-cols-2" : ""}`}>
        <CohortCard
          label={
            samePlatformIsHeadline
              ? "Your platform"
              : "All competitors"
          }
          benchmark={primary}
          percentile={scores.percentile}
          userScore={scores.overall_score}
          emphasis
        />
        {showBoth && wide && (
          <CohortCard
            label="The wider category"
            benchmark={wide}
            percentile={scores.category_percentile ?? 0}
            userScore={scores.overall_score}
            emphasis={false}
          />
        )}
      </div>

      {!samePlatformIsHeadline && (
        <p
          role="note"
          className="mt-3 text-xs text-amber-700 bg-amber-500/5 border border-amber-500/30 rounded-lg px-3 py-2"
        >
          Too few competitors were found on your own platform to benchmark
          against, so the headline is measured across every competitor found.
        </p>
      )}

      {thin.length > 0 && (
        <p className="mt-3 text-xs text-amber-700">
          Measured on fewer than 3 competitors:{" "}
          {thin.map((d) => `${d.dimension} (n=${d.n})`).join(", ")}. Treat those
          gaps as indicative.
        </p>
      )}

      <button
        onClick={() => setOpen(!open)}
        className="mt-4 text-xs font-semibold text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
      >
        {open ? "Hide" : "Show"} every competitor&rsquo;s score
      </button>

      {open && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-[var(--text-muted)] border-b border-[var(--card-border)]">
                <th className="py-2 pr-3 font-semibold">#</th>
                <th className="py-2 pr-3 font-semibold">Competitor</th>
                <th className="py-2 pr-3 font-semibold">Platform</th>
                <th className="py-2 font-semibold text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {[...(wide ?? primary).competitors]
                .sort((a, b) => b.overall_score - a.overall_score)
                .map((row) => (
                  <tr
                    key={`${row.rank}-${row.title}`}
                    className="border-b border-[var(--card-border)]/50"
                  >
                    <td className="py-2 pr-3 text-[var(--text-muted)]">
                      {row.rank}
                    </td>
                    <td className="py-2 pr-3">{row.brand_name || row.title}</td>
                    <td className="py-2 pr-3 text-[var(--text-muted)]">
                      {platformLabel(row.platform)}
                    </td>
                    <td
                      className="py-2 text-right font-bold"
                      style={{ color: scoreColor(row.overall_score) }}
                    >
                      {row.overall_score.toFixed(1)}
                    </td>
                  </tr>
                ))}
              <tr className="bg-[var(--accent)]/5">
                <td className="py-2 pr-3" />
                <td className="py-2 pr-3 font-bold">Your listing</td>
                <td className="py-2 pr-3 text-[var(--text-muted)]">&mdash;</td>
                <td
                  className="py-2 text-right font-black"
                  style={{ color: scoreColor(scores.overall_score) }}
                >
                  {scores.overall_score.toFixed(1)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
