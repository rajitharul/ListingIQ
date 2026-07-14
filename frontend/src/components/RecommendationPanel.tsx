"use client";

import { useState } from "react";
import type { RecommendationResult, Recommendation } from "@/types";

interface Props {
  recommendations: RecommendationResult;
}

function getImpactColor(impact: string): string {
  if (impact === "high") return "var(--score-low)";
  if (impact === "medium") return "var(--score-mid)";
  return "var(--score-high)";
}

function getImpactBg(impact: string): string {
  if (impact === "high") return "rgba(220, 38, 38, 0.08)";
  if (impact === "medium") return "rgba(217, 119, 6, 0.08)";
  return "rgba(22, 163, 74, 0.08)";
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(rec.specific_copy);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="bg-[var(--background)] border border-[var(--card-border)] rounded-xl p-4 hover:border-[var(--accent)]/30 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-[var(--text-muted)] bg-[var(--card-border)] rounded-full w-6 h-6 flex items-center justify-center">
            {rec.priority}
          </span>
          <span className="text-xs font-semibold">{rec.dimension}</span>
        </div>
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase"
          style={{
            color: getImpactColor(rec.impact),
            background: getImpactBg(rec.impact),
          }}
        >
          {rec.impact} impact
        </span>
      </div>

      <div className="flex items-center gap-3 mb-3 text-xs">
        <span className="text-[var(--text-muted)]">
          Score: <span className="font-bold">{rec.current_score.toFixed(1)}</span>
        </span>
        <span className="text-[var(--accent)]">&rarr;</span>
        <span className="text-[var(--score-high)]">
          <span className="font-bold">{rec.projected_score.toFixed(1)}</span>
        </span>
        <span className="text-[10px] text-[var(--text-muted)]">
          ({rec.expected_lift})
        </span>
      </div>

      <div className="bg-white rounded-lg p-3 mb-2 border border-[var(--card-border)]/50 relative group">
        <p className="text-sm text-[var(--foreground)] pr-8">{rec.specific_copy}</p>
        <button
          onClick={handleCopy}
          className="absolute top-2 right-2 text-[10px] px-2 py-1 rounded bg-[var(--card-border)] hover:bg-[var(--accent)] hover:text-white transition-colors opacity-0 group-hover:opacity-100"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      <p className="text-[10px] text-[var(--text-muted)]">
        {rec.competitive_evidence}
      </p>
    </div>
  );
}

export default function RecommendationPanel({ recommendations }: Props) {
  const [tab, setTab] = useState<"quick" | "strategic">("quick");

  const quickWins = recommendations.quick_wins;
  const strategic = recommendations.strategic_moves;

  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-2">Recommendations</h2>
      <p className="text-sm text-[var(--text-muted)] mb-4">
        Prioritized improvements with specific copy suggestions
      </p>

      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setTab("quick")}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors ${
            tab === "quick"
              ? "bg-[var(--accent)] text-white"
              : "bg-[var(--background)] text-[var(--text-muted)] border border-[var(--card-border)]"
          }`}
        >
          Quick Wins ({quickWins.length})
        </button>
        <button
          onClick={() => setTab("strategic")}
          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-colors ${
            tab === "strategic"
              ? "bg-[var(--accent)] text-white"
              : "bg-[var(--background)] text-[var(--text-muted)] border border-[var(--card-border)]"
          }`}
        >
          Strategic Moves ({strategic.length})
        </button>
      </div>

      <div className="space-y-3">
        {(tab === "quick" ? quickWins : strategic).map((rec, i) => (
          <RecommendationCard key={i} rec={rec} />
        ))}
        {(tab === "quick" ? quickWins : strategic).length === 0 && (
          <p className="text-sm text-[var(--text-muted)] text-center py-6">
            No {tab === "quick" ? "quick wins" : "strategic moves"} identified
          </p>
        )}
      </div>
    </div>
  );
}
