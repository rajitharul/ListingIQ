"use client";

import { useState } from "react";
import type { ListingInput } from "@/types";
import { addGuideline } from "@/lib/api";

interface Props {
  listingInput: ListingInput;
  memoryContext: {
    brand_name: string;
    guideline: string;
    source: string;
    confidence: number;
  }[];
}

export default function FeedbackPanel({ listingInput, memoryContext }: Props) {
  const [guideline, setGuideline] = useState("");
  const [saved, setSaved] = useState(false);

  const handleAddGuideline = async () => {
    if (!guideline.trim()) return;
    await addGuideline(listingInput.brand_name, guideline);
    setSaved(true);
    setGuideline("");
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-2">
        Agentic Memory &amp; Guidelines
      </h2>
      <p className="text-sm text-[var(--text-muted)] mb-6">
        Add brand guidelines to teach the AI your preferences. These persist
        across sessions.
      </p>

      <div className="flex gap-2 mb-6">
        <input
          value={guideline}
          onChange={(e) => setGuideline(e.target.value)}
          placeholder="e.g. 'Never use the word cheap — use affordable instead'"
          className="flex-1 bg-[var(--background)] border border-[var(--card-border)] rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
        <button
          onClick={handleAddGuideline}
          className="px-5 py-2.5 rounded-xl bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
        >
          {saved ? "Saved" : "Add Guideline"}
        </button>
      </div>

      {memoryContext.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Active Memory ({memoryContext.length} entries)
          </h3>
          <div className="space-y-2">
            {memoryContext.map((entry, i) => (
              <div
                key={i}
                className="flex items-start gap-3 bg-[var(--background)] border border-[var(--card-border)] rounded-lg p-3"
              >
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full mt-0.5 ${
                    entry.source === "brand_guideline"
                      ? "bg-[var(--accent)]/15 text-[var(--accent-light)]"
                      : entry.source === "human_feedback"
                        ? "bg-[var(--score-mid)]/15 text-[var(--score-mid)]"
                        : "bg-[var(--score-high)]/15 text-[var(--score-high)]"
                  }`}
                >
                  {entry.source.replace("_", " ")}
                </span>
                <p className="text-xs text-[var(--foreground)]/80 flex-1">
                  {entry.guideline}
                </p>
                <span className="text-[10px] text-[var(--text-muted)]">
                  {(entry.confidence * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {memoryContext.length === 0 && (
        <div className="text-center py-6 text-[var(--text-muted)]">
          <p className="text-sm">No guidelines cached yet</p>
          <p className="text-xs mt-1">
            Add brand guidelines or interact with suggestions to build memory
          </p>
        </div>
      )}
    </div>
  );
}
