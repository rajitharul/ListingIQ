"use client";

import { useState } from "react";
import type {
  ImprovementSuggestion,
  BrandInput,
  EvaluationResult,
} from "@/types";
import { getImprovement, submitFeedback } from "@/lib/api";

interface Props {
  suggestions: ImprovementSuggestion[];
  brandInput: BrandInput;
  evaluation: EvaluationResult;
  onNewSuggestions: (suggestions: ImprovementSuggestion[]) => void;
  onApplySuggestion: (newTagline: string) => void;
}

function getScoreColor(score: number): string {
  if (score >= 7.5) return "var(--score-high)";
  if (score >= 5.0) return "var(--score-mid)";
  return "var(--score-low)";
}

export default function ImprovementPanel({
  suggestions,
  brandInput,
  evaluation,
  onNewSuggestions,
  onApplySuggestion,
}: Props) {
  const [loadingDim, setLoadingDim] = useState<string | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [showFeedback, setShowFeedback] = useState<number | null>(null);

  const handleDimensionDrill = async (dimension: string) => {
    setLoadingDim(dimension);
    try {
      const newSuggestions = await getImprovement(
        brandInput,
        dimension,
        evaluation
      );
      onNewSuggestions(newSuggestions);
    } finally {
      setLoadingDim(null);
    }
  };

  const handleAccept = async (suggestion: ImprovementSuggestion) => {
    await submitFeedback({
      session_id: `session_${Date.now()}`,
      brand_name: brandInput.brand_name,
      feedback_type: "accepted",
      original_content: suggestion.original_text,
      suggested_content: suggestion.improved_text,
      dimension: suggestion.target_dimension,
    });
    onApplySuggestion(suggestion.improved_text);
  };

  const handleReject = async (
    index: number,
    suggestion: ImprovementSuggestion
  ) => {
    if (showFeedback === index && feedbackComment) {
      await submitFeedback({
        session_id: `session_${Date.now()}`,
        brand_name: brandInput.brand_name,
        feedback_type: "rejected",
        original_content: suggestion.original_text,
        suggested_content: suggestion.improved_text,
        user_comment: feedbackComment,
        dimension: suggestion.target_dimension,
      });
      setShowFeedback(null);
      setFeedbackComment("");
    } else {
      setShowFeedback(index);
    }
  };

  return (
    <div className="glass-card p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold">Targeted Improvements</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Surgical edits to boost specific dimensional scores
          </p>
        </div>
      </div>

      {/* Dimension quick-select */}
      <div className="flex flex-wrap gap-2 mb-6">
        {evaluation.dimensions.map((dim) => {
          const userDimScore = evaluation.user_score.dimension_scores.find(
            (ds) => ds.dimension === dim.name
          );
          return (
            <button
              key={dim.name}
              onClick={() => handleDimensionDrill(dim.name)}
              disabled={loadingDim !== null}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[var(--card-border)] hover:border-[var(--accent)]/50 transition-colors text-xs"
            >
              <span className="font-medium">{dim.name}</span>
              {userDimScore && (
                <span
                  className="font-bold"
                  style={{ color: getScoreColor(userDimScore.score) }}
                >
                  {userDimScore.score.toFixed(1)}
                </span>
              )}
              {loadingDim === dim.name && (
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              )}
            </button>
          );
        })}
      </div>

      {/* Suggestions */}
      <div className="space-y-4">
        {suggestions.map((suggestion, i) => (
          <div
            key={i}
            className="bg-[var(--background)] border border-[var(--card-border)] rounded-xl p-5"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <span className="px-2.5 py-0.5 rounded-lg bg-[var(--accent)]/10 text-[var(--accent-light)] text-xs font-medium">
                {suggestion.target_dimension}
              </span>
              <div className="flex items-center gap-1">
                <span
                  className="text-sm font-bold"
                  style={{
                    color: getScoreColor(suggestion.current_score),
                  }}
                >
                  {suggestion.current_score.toFixed(1)}
                </span>
                <span className="text-[var(--text-muted)]">&rarr;</span>
                <span
                  className="text-sm font-bold"
                  style={{
                    color: getScoreColor(suggestion.projected_score),
                  }}
                >
                  {suggestion.projected_score.toFixed(1)}
                </span>
                <span className="text-xs text-[var(--score-high)] ml-1">
                  (+
                  {(
                    suggestion.projected_score - suggestion.current_score
                  ).toFixed(1)}
                  )
                </span>
              </div>
            </div>

            {/* Before/After */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
                  Current
                </span>
                <p className="text-sm mt-1 text-[var(--foreground)]/60 line-through">
                  &ldquo;{suggestion.original_text}&rdquo;
                </p>
              </div>
              <div>
                <span className="text-[10px] text-[var(--score-high)] uppercase tracking-wider">
                  Improved
                </span>
                <p className="text-sm mt-1 font-medium">
                  &ldquo;{suggestion.improved_text}&rdquo;
                </p>
              </div>
            </div>

            {/* Changes */}
            <div className="mb-3">
              <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">
                Changes
              </span>
              <div className="mt-1 space-y-1">
                {suggestion.changes_made.map((change, j) => (
                  <div key={j} className="flex items-start gap-1.5">
                    <span className="text-[var(--score-high)] mt-0.5">+</span>
                    <span className="text-xs text-[var(--foreground)]/70">
                      {change}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Trade-offs */}
            {suggestion.trade_offs.length > 0 && (
              <div className="mb-3">
                <span className="text-[10px] text-[var(--score-mid)] uppercase tracking-wider">
                  Trade-offs
                </span>
                <div className="mt-1 space-y-1">
                  {suggestion.trade_offs.map((tradeoff, j) => (
                    <div key={j} className="flex items-start gap-1.5">
                      <span className="text-[var(--score-mid)] mt-0.5">
                        !
                      </span>
                      <span className="text-xs text-[var(--foreground)]/70">
                        {tradeoff}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 pt-3 border-t border-[var(--card-border)]">
              <button
                onClick={() => handleAccept(suggestion)}
                className="px-4 py-1.5 rounded-lg bg-[var(--score-high)]/15 text-[var(--score-high)] text-xs font-medium hover:bg-[var(--score-high)]/25 transition-colors"
              >
                Apply &amp; Re-score
              </button>
              <button
                onClick={() => handleReject(i, suggestion)}
                className="px-4 py-1.5 rounded-lg bg-[var(--score-low)]/15 text-[var(--score-low)] text-xs font-medium hover:bg-[var(--score-low)]/25 transition-colors"
              >
                Reject
              </button>
            </div>

            {/* Reject feedback */}
            {showFeedback === i && (
              <div className="mt-3 flex gap-2">
                <input
                  value={feedbackComment}
                  onChange={(e) => setFeedbackComment(e.target.value)}
                  placeholder="Why doesn't this work? (helps the AI learn)"
                  className="flex-1 bg-[var(--card-bg)] border border-[var(--card-border)] rounded-lg px-3 py-1.5 text-xs focus:outline-none focus:border-[var(--accent)]"
                />
                <button
                  onClick={() => handleReject(i, suggestion)}
                  className="px-3 py-1.5 rounded-lg bg-[var(--accent)] text-white text-xs font-medium"
                >
                  Submit
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
