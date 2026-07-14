"use client";

import { useState } from "react";
import Header from "@/components/Header";
import ListingInputForm from "@/components/ListingInputForm";
import CompetitorCards from "@/components/CompetitorCards";
import CompetitorAnalysisPanel from "@/components/CompetitorAnalysisPanel";
import ScoreMatrix from "@/components/ScoreMatrix";
import RadarChartComponent from "@/components/RadarChart";
import RecommendationPanel from "@/components/RecommendationPanel";
import RewritePanel from "@/components/RewritePanel";
import FeedbackPanel from "@/components/FeedbackPanel";
import AgentVisualizer from "@/components/AgentVisualizer";
import LoadingOverlay from "@/components/LoadingOverlay";
import { runPipelineStream } from "@/lib/api";
import type { ListingInput, FullPipelineResponse } from "@/types";

export default function Home() {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<FullPipelineResponse | null>(null);
  const [listingInput, setListingInput] = useState<ListingInput | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [completedNodes, setCompletedNodes] = useState<string[]>([]);

  const handleSubmit = async (input: ListingInput) => {
    setIsLoading(true);
    setError(null);
    setListingInput(input);
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
                <span className="bg-gradient-to-r from-emerald-600 to-emerald-400 bg-clip-text text-transparent">
                  Optimize Your Product Listings
                </span>{" "}
                with AI
              </h1>
              <p className="text-lg text-[var(--text-muted)] max-w-2xl mx-auto">
                Score your ecommerce listings against the top 10 competitors using an
                8-agent AI pipeline. Get per-dimension scores, targeted
                recommendations, and optimized rewrites.
              </p>
            </div>
          )}

          {/* Input form */}
          <ListingInputForm onSubmit={handleSubmit} isLoading={isLoading} />

          {/* Error */}
          {error && (
            <div className="glass-card p-6 border-[var(--score-low)]/30 bg-[var(--score-low)]/5">
              <p className="text-sm text-[var(--score-low)]">{error}</p>
            </div>
          )}

          {/* Results */}
          {result && listingInput && (
            <>
              {/* Overall score hero */}
              <div className="glass-card p-8 text-center">
                <p className="text-sm text-[var(--text-muted)] mb-2">
                  Your Overall Score
                </p>
                <div className="flex items-center justify-center gap-3">
                  <span
                    className="text-6xl font-black"
                    style={{
                      color:
                        result.scores.overall_score >= 7.5
                          ? "var(--score-high)"
                          : result.scores.overall_score >= 5
                            ? "var(--score-mid)"
                            : "var(--score-low)",
                    }}
                  >
                    {result.scores.overall_score.toFixed(1)}
                  </span>
                  <span className="text-2xl text-[var(--text-muted)]">
                    /10
                  </span>
                </div>
                <p className="text-sm text-[var(--text-muted)] mt-2">
                  Percentile{" "}
                  <span className="font-bold text-[var(--foreground)]">
                    P{result.scores.percentile}
                  </span>{" "}
                  &middot; {result.category.vertical} &rarr; {result.category.subcategory}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  &ldquo;{listingInput.product_title}&rdquo;
                </p>
              </div>

              {/* Agent Pipeline Visualizer */}
              {result.agent_trace && (
                <AgentVisualizer trace={result.agent_trace} />
              )}

              {/* Competitor listings */}
              <CompetitorCards data={result.competitors} />

              {/* Competitor analysis */}
              <CompetitorAnalysisPanel analysis={result.competitor_analysis} />

              {/* Score matrix + Radar side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="lg:col-span-2">
                  <ScoreMatrix scores={result.scores} />
                </div>
                <div>
                  <RadarChartComponent scores={result.scores} />
                </div>
              </div>

              {/* Recommendations */}
              <RecommendationPanel recommendations={result.recommendations} />

              {/* Rewrites */}
              <RewritePanel
                rewrites={result.rewrites}
                originalTitle={result.parsed_listing.original_title}
                originalBullets={result.parsed_listing.original_bullets}
                originalDescription={result.parsed_listing.original_description}
              />

              {/* Feedback & Memory */}
              <FeedbackPanel
                listingInput={listingInput}
                memoryContext={[]}
              />
            </>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--card-border)] py-6 text-center">
        <p className="text-xs text-[var(--text-muted)]">
          ListingIQ v1.0 — 8-Agent Product Listing Optimization Engine | Powered by GPT-4o
        </p>
      </footer>
    </div>
  );
}
