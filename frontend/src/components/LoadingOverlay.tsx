"use client";

import { useState, useEffect } from "react";

const PIPELINE_STEPS = [
  {
    agent: "Input Parser",
    description: "Extracting entities, ingredients, certifications, and claims from your listing...",
    nodeKey: "input_parser",
  },
  {
    agent: "Category Classifier",
    description: "Identifying product vertical, category, and loading scoring rubric...",
    nodeKey: "category_classifier",
  },
  {
    agent: "Competitor Scout",
    description: "Researching top 10 competitor listings in your subcategory...",
    nodeKey: "competitor_scout",
  },
  {
    agent: "Listing Analyzer",
    description: "Evaluating your listing against each rubric dimension...",
    nodeKey: "listing_analyzer",
  },
  {
    agent: "Competitor Analyzer",
    description: "Extracting keyword patterns, claim frequency, and trust signals...",
    nodeKey: "competitor_analyzer",
  },
  {
    agent: "Benchmark Scorer",
    description: "Scoring your listing per dimension against competitor benchmarks...",
    nodeKey: "benchmark_scorer",
  },
  {
    agent: "Recommendation Engine",
    description: "Generating prioritized improvements with specific copy suggestions...",
    nodeKey: "recommendation_engine",
  },
  {
    agent: "Rewrite Generator",
    description: "Creating 3 optimized listing variants — keyword, benefit-led, trust-forward...",
    nodeKey: "rewrite_generator",
  },
];

interface Props {
  isVisible: boolean;
  completedNodes?: string[];
}

export default function LoadingOverlay({ isVisible, completedNodes = [] }: Props) {
  const [fallbackStep, setFallbackStep] = useState(0);
  const isStreaming = completedNodes.length > 0;

  useEffect(() => {
    if (!isVisible || isStreaming) {
      setFallbackStep(0);
      return;
    }
    const interval = setInterval(() => {
      setFallbackStep((prev) =>
        prev < PIPELINE_STEPS.length - 1 ? prev + 1 : prev
      );
    }, 4000);
    return () => clearInterval(interval);
  }, [isVisible, isStreaming]);

  const getStepStatus = (index: number): "done" | "active" | "pending" => {
    if (isStreaming) {
      const step = PIPELINE_STEPS[index];
      if (completedNodes.includes(step.nodeKey)) return "done";
      const firstPending = PIPELINE_STEPS.findIndex(
        (s) => !completedNodes.includes(s.nodeKey)
      );
      return index === firstPending ? "active" : "pending";
    }
    if (index < fallbackStep) return "done";
    if (index === fallbackStep) return "active";
    return "pending";
  };

  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 z-50 bg-white/90 backdrop-blur-sm flex items-center justify-center">
      <div className="glass-card pulse-glow p-10 max-w-lg w-full mx-4">
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-emerald-600 to-emerald-500 flex items-center justify-center">
            <svg
              className="animate-spin h-8 w-8 text-white"
              viewBox="0 0 24 24"
            >
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
          </div>
          <h2 className="text-xl font-bold">8-Agent Pipeline Running</h2>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            8 specialized AI agents analyzing your product listing
          </p>
        </div>

        <div className="space-y-3">
          {PIPELINE_STEPS.map((step, i) => {
            const status = getStepStatus(i);
            return (
            <div
              key={i}
              className={`flex items-center gap-3 p-3 rounded-xl transition-all duration-500 ${
                status === "done"
                  ? "bg-[var(--score-high)]/10 border border-[var(--score-high)]/20"
                  : status === "active"
                    ? "bg-[var(--accent)]/10 border border-[var(--accent)]/30"
                    : "opacity-30"
              }`}
            >
              <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0">
                {status === "done" ? (
                  <span className="text-[var(--score-high)] text-sm">
                    &#10003;
                  </span>
                ) : status === "active" ? (
                  <svg
                    className="animate-spin h-4 w-4 text-[var(--accent-light)]"
                    viewBox="0 0 24 24"
                  >
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
                ) : (
                  <span className="text-[var(--text-muted)] text-xs">
                    &#9675;
                  </span>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold">{step.agent}</div>
                <div className="text-[10px] text-[var(--text-muted)] truncate">
                  {step.description}
                </div>
              </div>
            </div>
          )})}
        </div>
      </div>
    </div>
  );
}
