"use client";

import type { ListingScore } from "@/types";

interface Props {
  scores: ListingScore;
}

function getScoreColor(score: number): string {
  if (score >= 7.5) return "var(--score-high)";
  if (score >= 5.0) return "var(--score-mid)";
  return "var(--score-low)";
}

function getScoreBg(score: number): string {
  if (score >= 7.5) return "rgba(22, 163, 74, 0.08)";
  if (score >= 5.0) return "rgba(217, 119, 6, 0.08)";
  return "rgba(220, 38, 38, 0.08)";
}

function getGapColor(gap: number): string {
  if (gap >= 2) return "var(--score-low)";
  if (gap >= 1) return "var(--score-mid)";
  return "var(--score-high)";
}

export default function ScoreMatrix({ scores }: Props) {
  const sorted = [...scores.dimension_scores].sort((a, b) => b.weight - a.weight);

  return (
    <div className="glass-card p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Dimension Scores</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Per-dimension scoring against competitor benchmarks
          </p>
        </div>
        <div className="text-right">
          <span className="text-xs text-[var(--text-muted)]">Percentile</span>
          <div className="text-lg font-bold" style={{ color: getScoreColor(scores.percentile / 10) }}>
            P{scores.percentile}
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--card-border)]">
              <th className="text-left text-xs font-medium text-[var(--text-muted)] pb-3 pr-4">
                Dimension
              </th>
              <th className="text-center text-xs font-medium text-[var(--text-muted)] pb-3 px-2 w-16">
                Weight
              </th>
              <th className="text-center text-xs font-medium text-[var(--accent-light)] pb-3 px-2 w-16">
                You
              </th>
              <th className="text-center text-xs font-medium text-[var(--text-muted)] pb-3 px-2 w-16">
                Comp Avg
              </th>
              <th className="text-center text-xs font-medium text-[var(--text-muted)] pb-3 px-2 w-16">
                Gap
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((dim) => {
              const gap = dim.competitor_avg - dim.score;
              return (
                <tr
                  key={dim.dimension}
                  className="border-b border-[var(--card-border)]/50 hover:bg-[var(--accent)]/5 transition-colors"
                >
                  <td className="py-3 pr-4">
                    <div className="text-sm font-medium">{dim.dimension}</div>
                    {dim.weaknesses.length > 0 && (
                      <div className="text-[10px] text-[var(--score-low)] mt-0.5 line-clamp-1">
                        {dim.weaknesses[0]}
                      </div>
                    )}
                    {dim.weaknesses.length === 0 && dim.strengths.length > 0 && (
                      <div className="text-[10px] text-[var(--score-high)] mt-0.5 line-clamp-1">
                        {dim.strengths[0]}
                      </div>
                    )}
                  </td>
                  <td className="text-center px-2 py-3">
                    <span className="text-xs text-[var(--text-muted)]">
                      {(dim.weight * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="text-center px-2 py-3">
                    <div
                      className="inline-flex items-center justify-center w-12 h-7 rounded-lg text-sm font-bold"
                      style={{
                        color: getScoreColor(dim.score),
                        background: getScoreBg(dim.score),
                      }}
                    >
                      {dim.score.toFixed(1)}
                    </div>
                  </td>
                  <td className="text-center px-2 py-3">
                    <span className="text-sm text-[var(--text-muted)]">
                      {dim.competitor_avg.toFixed(1)}
                    </span>
                  </td>
                  <td className="text-center px-2 py-3">
                    <span
                      className="text-xs font-bold"
                      style={{ color: getGapColor(gap) }}
                    >
                      {gap > 0 ? `-${gap.toFixed(1)}` : gap === 0 ? "0" : `+${Math.abs(gap).toFixed(1)}`}
                    </span>
                  </td>
                </tr>
              );
            })}
            {/* Overall row */}
            <tr className="bg-[var(--accent)]/5">
              <td className="py-4 pr-4">
                <div className="text-sm font-bold">OVERALL (Weighted)</div>
              </td>
              <td className="text-center px-2 py-4">
                <span className="text-xs text-[var(--text-muted)]">100%</span>
              </td>
              <td className="text-center px-2 py-4">
                <span
                  className="text-lg font-black"
                  style={{ color: getScoreColor(scores.overall_score) }}
                >
                  {scores.overall_score.toFixed(1)}
                </span>
              </td>
              <td className="text-center px-2 py-4" colSpan={2} />
            </tr>
          </tbody>
        </table>
      </div>

      {/* Explanation accordion */}
      <details className="mt-4">
        <summary className="text-xs text-[var(--text-muted)] cursor-pointer hover:text-[var(--accent)]">
          Show detailed explanations
        </summary>
        <div className="mt-3 space-y-3">
          {sorted.map((dim) => (
            <div key={dim.dimension} className="bg-[var(--background)] rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-semibold">{dim.dimension}</span>
                <span
                  className="text-xs font-bold"
                  style={{ color: getScoreColor(dim.score) }}
                >
                  {dim.score.toFixed(1)}/10
                </span>
              </div>
              <p className="text-xs text-[var(--text-muted)]">{dim.explanation}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
