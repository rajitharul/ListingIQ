"use client";

import type { FullPipelineResponse } from "@/types";

interface Props {
  result: FullPipelineResponse;
}

export default function TrendProjectionPanel({ result }: Props) {
  const data = result.trend_projection_data as Record<string, unknown> | null;
  if (!data) return null;

  const hasHistory = data.has_history as boolean;

  if (!hasHistory) {
    return (
      <div className="glass-card p-6">
        <h2 className="text-lg font-semibold mb-2">Score Trend Projection</h2>
        <p className="text-sm text-[var(--text-muted)]">
          {data.message as string}
        </p>
        <p className="text-xs text-[var(--text-muted)] mt-2">
          Data points: {data.data_points as number} (need at least 2)
        </p>
      </div>
    );
  }

  const trajectory = data.trajectory as string;
  const projectedScore = data.projected_next_score as number;
  const confidence = data.confidence as number;
  const summary = data.trend_summary as string;
  const recommendations = (data.recommendations as string[]) || [];
  const scoreHistory = (data.score_history as Array<{ date: string; score: number }>) || [];

  const trajectoryColor =
    trajectory === "improving"
      ? "var(--score-high)"
      : trajectory === "declining"
        ? "var(--score-low)"
        : "var(--score-mid)";

  const trajectoryIcon =
    trajectory === "improving" ? "▲" : trajectory === "declining" ? "▼" : "►";

  return (
    <div className="glass-card p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Score Trend Projection</h2>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Historical analysis and predictive projection
        </p>
      </div>

      {/* Trajectory + Projected Score */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="p-4 rounded-xl border border-[var(--card-border)] text-center">
          <p className="text-xs text-[var(--text-muted)] mb-1">Trajectory</p>
          <p className="text-2xl font-bold" style={{ color: trajectoryColor }}>
            {trajectoryIcon} {trajectory}
          </p>
        </div>
        <div className="p-4 rounded-xl border border-[var(--card-border)] text-center">
          <p className="text-xs text-[var(--text-muted)] mb-1">
            Projected Next Score
          </p>
          <p className="text-2xl font-bold" style={{ color: trajectoryColor }}>
            {typeof projectedScore === "number" ? projectedScore.toFixed(1) : projectedScore}
          </p>
        </div>
        <div className="p-4 rounded-xl border border-[var(--card-border)] text-center">
          <p className="text-xs text-[var(--text-muted)] mb-1">Confidence</p>
          <p className="text-2xl font-bold">
            {typeof confidence === "number" ? `${(confidence * 100).toFixed(0)}%` : confidence}
          </p>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="mb-4 p-4 rounded-xl bg-[var(--accent)]/10 border border-[var(--accent)]/20">
          <p className="text-sm">{summary}</p>
        </div>
      )}

      {/* Score History Mini Chart */}
      {scoreHistory.length > 0 && (
        <div className="mb-4">
          <p className="text-xs font-medium text-[var(--text-muted)] mb-2">
            Score History
          </p>
          <div className="flex items-end gap-1 h-16">
            {scoreHistory.map((point, i) => {
              const height = Math.max(10, (point.score / 10) * 100);
              return (
                <div
                  key={i}
                  className="flex-1 rounded-t-sm bg-gradient-to-t from-red-500 to-red-400 relative group"
                  style={{ height: `${height}%` }}
                  title={`${point.date}: ${point.score}/10`}
                >
                  <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                    {point.score}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div>
          <p className="text-xs font-medium text-[var(--text-muted)] mb-2">
            Data-Driven Recommendations
          </p>
          <ul className="space-y-1">
            {recommendations.map((rec, i) => (
              <li key={i} className="text-xs text-[var(--text-muted)]">
                &bull; {rec}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
