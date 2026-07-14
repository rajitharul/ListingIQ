"use client";

import type { CompetitorAnalysis } from "@/types";

interface Props {
  analysis: CompetitorAnalysis;
}

export default function CompetitorAnalysisPanel({ analysis }: Props) {
  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-2">Competitor Analysis</h2>
      <p className="text-sm text-[var(--text-muted)] mb-6">
        {analysis.summary}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Keyword Patterns */}
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Top Keywords
          </h3>
          <div className="space-y-2">
            {analysis.keyword_patterns.slice(0, 10).map((kw, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-[var(--background)] rounded-lg px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold text-[var(--text-muted)] w-4">
                    {i + 1}
                  </span>
                  <span className="text-xs font-medium">{kw.keyword}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[var(--text-muted)]">
                    {kw.position}
                  </span>
                  <span className="text-xs font-bold text-[var(--accent)]">
                    {kw.frequency}x
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Claim Patterns */}
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Common Claims
          </h3>
          <div className="space-y-2">
            {analysis.claim_patterns.slice(0, 8).map((cp, i) => (
              <div
                key={i}
                className="bg-[var(--background)] rounded-lg px-3 py-2"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium">{cp.claim}</span>
                  <span className="text-xs font-bold text-[var(--accent)]">
                    {cp.frequency}x
                  </span>
                </div>
                <span className="text-[10px] text-[var(--text-muted)]">
                  e.g. {cp.example_brand}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Trust Signals */}
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Trust Signals
          </h3>
          <div className="space-y-2">
            {analysis.trust_signals.slice(0, 8).map((ts, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-[var(--background)] rounded-lg px-3 py-2"
              >
                <span className="text-xs font-medium">{ts.signal}</span>
                <span className="text-xs font-bold text-[var(--accent)]">
                  {ts.frequency}x
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Differentiation Insights */}
      {analysis.differentiation_insights.length > 0 && (
        <div className="mt-6 pt-4 border-t border-[var(--card-border)]">
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Differentiation Insights
          </h3>
          <div className="space-y-2">
            {analysis.differentiation_insights.map((insight, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] mt-1.5 shrink-0" />
                <p className="text-sm text-[var(--foreground)]/80">{insight}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
