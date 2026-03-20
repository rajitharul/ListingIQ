"use client";

import type { TrendAnalysisResult } from "@/types";

interface Props {
  trendData: TrendAnalysisResult;
}

function SentimentBadge({ score }: { score: number }) {
  const label =
    score > 0.3 ? "Positive" : score < -0.3 ? "Negative" : "Neutral";
  const color =
    score > 0.3
      ? "var(--score-high)"
      : score < -0.3
        ? "var(--score-low)"
        : "var(--score-mid)";
  return (
    <span
      className="inline-block px-2 py-0.5 rounded-lg text-xs font-medium"
      style={{ backgroundColor: `${color}20`, color }}
    >
      {label} ({score > 0 ? "+" : ""}
      {score.toFixed(2)})
    </span>
  );
}

function DirectionArrow({ direction }: { direction: string }) {
  if (direction === "rising")
    return <span className="text-[var(--score-high)]">&#9650;</span>;
  if (direction === "declining")
    return <span className="text-[var(--score-low)]">&#9660;</span>;
  return <span className="text-[var(--score-mid)]">&#9654;</span>;
}

export default function TrendPanel({ trendData }: Props) {
  const allTrends = [trendData.brand_trend, ...trendData.competitor_trends];

  return (
    <div className="glass-card p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Market Trends &amp; Sentiment</h2>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Real-time market signals from Google Trends and news analysis
        </p>
      </div>

      {/* Market Momentum */}
      {trendData.market_momentum && (
        <div className="mb-6 p-4 rounded-xl bg-[var(--accent)]/10 border border-[var(--accent)]/20">
          <p className="text-sm font-medium text-[var(--accent-light)]">
            Market Momentum
          </p>
          <p className="text-sm mt-1">{trendData.market_momentum}</p>
        </div>
      )}

      {/* Trend Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        {allTrends.map((trend) => (
          <div
            key={trend.competitor_name}
            className={`p-4 rounded-xl border ${
              trend.competitor_name === trendData.brand_trend.competitor_name
                ? "border-[var(--accent)]/30 bg-[var(--accent)]/5"
                : "border-[var(--card-border)]"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm">
                {trend.competitor_name}
              </span>
              <div className="flex items-center gap-2">
                <DirectionArrow direction={trend.trend_direction} />
                <SentimentBadge score={trend.sentiment_score} />
              </div>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-[var(--text-muted)]">
                Search Interest:
              </span>
              <div className="flex-1 h-2 bg-[var(--card-border)] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-red-500 to-red-400"
                  style={{ width: `${Math.min(trend.search_interest, 100)}%` }}
                />
              </div>
              <span className="text-xs font-mono">
                {trend.search_interest.toFixed(0)}
              </span>
            </div>
            {trend.recent_headlines.length > 0 && (
              <div className="mt-2 space-y-1">
                {trend.recent_headlines.slice(0, 2).map((hl, i) => (
                  <p
                    key={i}
                    className="text-xs text-[var(--text-muted)] truncate"
                    title={hl}
                  >
                    &bull; {hl}
                  </p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Opportunities & Threats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {trendData.opportunities.length > 0 && (
          <div className="p-4 rounded-xl bg-[var(--score-high)]/5 border border-[var(--score-high)]/20">
            <p className="text-sm font-medium text-[var(--score-high)] mb-2">
              Opportunities
            </p>
            <ul className="space-y-1">
              {trendData.opportunities.map((opp, i) => (
                <li
                  key={i}
                  className="text-xs text-[var(--text-muted)] flex gap-1.5"
                >
                  <span className="text-[var(--score-high)]">+</span>
                  {opp}
                </li>
              ))}
            </ul>
          </div>
        )}
        {trendData.threats.length > 0 && (
          <div className="p-4 rounded-xl bg-[var(--score-low)]/5 border border-[var(--score-low)]/20">
            <p className="text-sm font-medium text-[var(--score-low)] mb-2">
              Threats
            </p>
            <ul className="space-y-1">
              {trendData.threats.map((threat, i) => (
                <li
                  key={i}
                  className="text-xs text-[var(--text-muted)] flex gap-1.5"
                >
                  <span className="text-[var(--score-low)]">!</span>
                  {threat}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
