"use client";

import type { CompetitorAnalysisResult, ContentScore } from "@/types";

interface Props {
  data: CompetitorAnalysisResult;
  scores: ContentScore[];
}

function getScoreColor(score: number): string {
  if (score >= 7.5) return "text-[var(--score-high)]";
  if (score >= 5.0) return "text-[var(--score-mid)]";
  return "text-[var(--score-low)]";
}

export default function CompetitorCards({ data, scores }: Props) {
  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-2">Competitive Landscape</h2>
      <p className="text-sm text-[var(--text-muted)] mb-6">
        {data.market_summary}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.competitors.map((comp) => {
          const compScore = scores.find((s) => s.brand_name === comp.name);
          return (
            <div
              key={comp.name}
              className="bg-[var(--background)] border border-[var(--card-border)] rounded-xl p-5 hover:border-[var(--accent)]/30 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-sm">{comp.name}</h3>
                {compScore && (
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-2xl font-bold ${getScoreColor(compScore.overall_score)}`}
                    >
                      {compScore.overall_score.toFixed(1)}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      /10
                    </span>
                  </div>
                )}
              </div>
              <p className="text-[var(--accent-light)] text-sm font-medium mb-2">
                &ldquo;{comp.tagline}&rdquo;
              </p>
              <p className="text-xs text-[var(--text-muted)] mb-3 line-clamp-2">
                {comp.description}
              </p>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />
                <span className="text-xs text-[var(--text-muted)]">
                  {comp.market_position}
                </span>
              </div>
              {compScore && (
                <div className="mt-3 pt-3 border-t border-[var(--card-border)]">
                  <span className="text-xs text-[var(--text-muted)]">Rank</span>
                  <span className="ml-1 text-sm font-bold">
                    #{compScore.rank}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
