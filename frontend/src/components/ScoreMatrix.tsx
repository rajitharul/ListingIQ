"use client";

import type { EvaluationResult } from "@/types";

interface Props {
  evaluation: EvaluationResult;
  onDimensionClick: (dimension: string) => void;
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

export default function ScoreMatrix({ evaluation, onDimensionClick }: Props) {
  const { user_score, competitor_scores, dimensions, rankings } = evaluation;
  const allScores = [user_score, ...competitor_scores];

  return (
    <div className="glass-card p-8">
      {/* Rankings bar */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">
            Multi-Dimensional Score Matrix
          </h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Click any dimension to get targeted improvements
          </p>
        </div>
        <div className="flex items-center gap-3">
          {rankings.map((r, i) => (
            <div
              key={r.brand}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${
                r.brand === user_score.brand_name
                  ? "bg-[var(--accent)]/15 border border-[var(--accent)]/30"
                  : "bg-[var(--card-border)]"
              }`}
            >
              <span
                className="text-xs font-bold"
                style={{
                  color:
                    i === 0 ? "var(--score-high)" : "var(--text-muted)",
                }}
              >
                #{r.rank}
              </span>
              <span className="text-xs font-medium">{r.brand}</span>
              <span
                className="text-xs font-bold"
                style={{ color: getScoreColor(r.score) }}
              >
                {r.score.toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Matrix table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--card-border)]">
              <th className="text-left text-xs font-medium text-[var(--text-muted)] pb-3 pr-4 w-36">
                Dimension
              </th>
              {allScores.map((s) => (
                <th
                  key={s.brand_name}
                  className={`text-center text-xs font-medium pb-3 px-3 ${
                    s.brand_name === user_score.brand_name
                      ? "text-[var(--accent-light)]"
                      : "text-[var(--text-muted)]"
                  }`}
                >
                  {s.brand_name}
                  {s.brand_name === user_score.brand_name && (
                    <span className="ml-1 text-[10px] opacity-60">(You)</span>
                  )}
                </th>
              ))}
              <th className="text-center text-xs font-medium text-[var(--text-muted)] pb-3 px-3">
                Benchmark
              </th>
            </tr>
          </thead>
          <tbody>
            {dimensions.map((dim) => {
              return (
                <tr
                  key={dim.name}
                  onClick={() => onDimensionClick(dim.name)}
                  className="border-b border-[var(--card-border)]/50 hover:bg-[var(--accent)]/5 cursor-pointer transition-colors"
                >
                  <td className="py-3.5 pr-4">
                    <div className="text-sm font-medium">{dim.name}</div>
                    <div className="text-[10px] text-[var(--text-muted)] mt-0.5 line-clamp-1">
                      {dim.description}
                    </div>
                  </td>
                  {allScores.map((s) => {
                    const ds = s.dimension_scores.find(
                      (d) => d.dimension === dim.name
                    );
                    const score = ds?.score ?? 0;
                    const isUser =
                      s.brand_name === user_score.brand_name;
                    const isHighest =
                      score ===
                      Math.max(
                        ...allScores.map(
                          (as) =>
                            as.dimension_scores.find(
                              (d) => d.dimension === dim.name
                            )?.score ?? 0
                        )
                      );
                    return (
                      <td
                        key={s.brand_name}
                        className="text-center px-3 py-3.5"
                      >
                        <div
                          className="inline-flex items-center justify-center w-14 h-8 rounded-lg text-sm font-bold transition-score"
                          style={{
                            color: getScoreColor(score),
                            background: isUser
                              ? getScoreBg(score)
                              : "transparent",
                            border: isHighest
                              ? `1px solid ${getScoreColor(score)}`
                              : "1px solid transparent",
                          }}
                        >
                          {score.toFixed(1)}
                        </div>
                      </td>
                    );
                  })}
                  <td className="text-center px-3 py-3.5">
                    <span className="text-sm font-bold text-[var(--accent-light)] opacity-40">
                      10.0
                    </span>
                  </td>
                </tr>
              );
            })}
            {/* Overall row */}
            <tr className="bg-[var(--accent)]/5">
              <td className="py-4 pr-4">
                <div className="text-sm font-bold">OVERALL</div>
              </td>
              {allScores.map((s) => (
                <td key={s.brand_name} className="text-center px-3 py-4">
                  <span
                    className="text-lg font-black"
                    style={{ color: getScoreColor(s.overall_score) }}
                  >
                    {s.overall_score.toFixed(1)}
                  </span>
                </td>
              ))}
              <td className="text-center px-3 py-4">
                <span className="text-lg font-black text-[var(--accent-light)] opacity-40">
                  10.0
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Insights */}
      {evaluation.insights.length > 0 && (
        <div className="mt-6 pt-4 border-t border-[var(--card-border)]">
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Key Insights
          </h3>
          <div className="space-y-2">
            {evaluation.insights.map((insight, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] mt-1.5 shrink-0" />
                <p className="text-sm text-[var(--foreground)]/80">
                  {insight}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
