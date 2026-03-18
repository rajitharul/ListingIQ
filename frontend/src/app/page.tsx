"use client";

import { useState } from "react";
import Header from "@/components/Header";
import BrandInputForm from "@/components/BrandInputForm";
import CompetitorCards from "@/components/CompetitorCards";
import ScoreMatrix from "@/components/ScoreMatrix";
import RadarChartComponent from "@/components/RadarChart";
import ImprovementPanel from "@/components/ImprovementPanel";
import FeedbackPanel from "@/components/FeedbackPanel";
import LoadingOverlay from "@/components/LoadingOverlay";
import { runPipeline, runPipelineStream } from "@/lib/api";
import type {
  BrandInput,
  FullPipelineResponse,
  ImprovementSuggestion,
} from "@/types";

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<FullPipelineResponse | null>(null);
  const [brandInput, setBrandInput] = useState<BrandInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completedNodes, setCompletedNodes] = useState<string[]>([]);

  const handleSubmit = async (input: BrandInput) => {
    setIsLoading(true);
    setError(null);
    setBrandInput(input);
    setCompletedNodes([]);
    try {
      const response = await runPipelineStream(input, (node) => {
        setCompletedNodes((prev) => [...prev, node]);
      });
      setResult(response);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Pipeline failed. Check that the backend is running."
      );
    } finally {
      setIsLoading(false);
      setCompletedNodes([]);
    }
  };

  const handleNewSuggestions = (suggestions: ImprovementSuggestion[]) => {
    if (result) {
      setResult({ ...result, suggestions });
    }
  };

  const handleApplySuggestion = async (newTagline: string) => {
    if (!brandInput) return;
    const updatedInput = { ...brandInput, current_tagline: newTagline };
    setBrandInput(updatedInput);
    // Re-run the full pipeline with the new tagline
    setIsLoading(true);
    setCompletedNodes([]);
    try {
      const response = await runPipelineStream(updatedInput, (node) => {
        setCompletedNodes((prev) => [...prev, node]);
      });
      setResult(response);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Re-evaluation failed."
      );
    } finally {
      setIsLoading(false);
      setCompletedNodes([]);
    }
  };

  const handleDimensionClick = async (dimension: string) => {
    if (!brandInput || !result) return;
    const panel = document.getElementById("improvements");
    panel?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <LoadingOverlay isVisible={isLoading} completedNodes={completedNodes} />

      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8">
        <div className="space-y-8">
          {/* Hero section */}
          {!result && (
            <div className="text-center py-12">
              <h1 className="text-4xl font-extrabold tracking-tight mb-3">
                <span className="bg-gradient-to-r from-red-600 to-red-400 bg-clip-text text-transparent">
                  Competitive Intelligence,
                </span>{" "}
                Quantified
              </h1>
              <p className="text-lg text-[var(--text-muted)] max-w-2xl mx-auto">
                Benchmark your marketing copy against real competitors using a
                6-agent AI pipeline. Get numerical scores, targeted
                improvements, and adaptive learning.
              </p>
            </div>
          )}

          {/* Input form */}
          <BrandInputForm onSubmit={handleSubmit} isLoading={isLoading} />

          {/* Error */}
          {error && (
            <div className="glass-card p-6 border-[var(--score-low)]/30 bg-[var(--score-low)]/5">
              <p className="text-sm text-[var(--score-low)]">{error}</p>
            </div>
          )}

          {/* Results */}
          {result && brandInput && (
            <>
              {/* User's current score hero */}
              <div className="glass-card p-8 text-center">
                <p className="text-sm text-[var(--text-muted)] mb-2">
                  Your Overall Score
                </p>
                <div className="flex items-center justify-center gap-3">
                  <span
                    className="text-6xl font-black"
                    style={{
                      color:
                        result.evaluation.user_score.overall_score >= 7.5
                          ? "var(--score-high)"
                          : result.evaluation.user_score.overall_score >= 5
                            ? "var(--score-mid)"
                            : "var(--score-low)",
                    }}
                  >
                    {result.evaluation.user_score.overall_score.toFixed(1)}
                  </span>
                  <span className="text-2xl text-[var(--text-muted)]">
                    /10
                  </span>
                </div>
                <p className="text-sm text-[var(--text-muted)] mt-2">
                  Rank{" "}
                  <span className="font-bold text-[var(--foreground)]">
                    #{result.evaluation.user_score.rank}
                  </span>{" "}
                  of {result.evaluation.rankings.length} brands &middot;
                  &ldquo;{brandInput.current_tagline}&rdquo;
                </p>
                <div className="mt-4 inline-block px-4 py-2 rounded-xl bg-[var(--accent)]/10 border border-[var(--accent)]/20">
                  <span className="text-xs text-[var(--text-muted)]">
                    Benchmark:{" "}
                  </span>
                  <span className="text-xs text-[var(--accent-light)] font-medium">
                    &ldquo;{result.evaluation.benchmark.ideal_tagline}&rdquo;
                  </span>
                </div>
              </div>

              {/* Competitor cards */}
              <CompetitorCards
                data={result.competitors}
                scores={result.evaluation.competitor_scores}
              />

              {/* Score matrix + Radar side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2">
                  <ScoreMatrix
                    evaluation={result.evaluation}
                    onDimensionClick={handleDimensionClick}
                  />
                </div>
                <div>
                  <RadarChartComponent evaluation={result.evaluation} />
                </div>
              </div>

              {/* Improvements */}
              <div id="improvements">
                <ImprovementPanel
                  suggestions={result.suggestions}
                  brandInput={brandInput}
                  evaluation={result.evaluation}
                  onNewSuggestions={handleNewSuggestions}
                  onApplySuggestion={handleApplySuggestion}
                />
              </div>

              {/* Feedback & Memory */}
              <FeedbackPanel
                brandInput={brandInput}
                memoryContext={result.memory_context}
              />
            </>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--card-border)] py-6 text-center">
        <p className="text-xs text-[var(--text-muted)]">
          Sitescore v1.0 — Multi-Agent Benchmarking Engine | Powered by GPT-4o
        </p>
      </footer>
    </div>
  );
}
