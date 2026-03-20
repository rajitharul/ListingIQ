"use client";

import type { FullPipelineResponse } from "@/types";

interface Props {
  result: FullPipelineResponse;
}

function Section({
  title,
  children,
  color = "var(--accent)",
}: {
  title: string;
  children: React.ReactNode;
  color?: string;
}) {
  return (
    <div className="p-5 rounded-xl border border-[var(--card-border)]">
      <h3 className="text-sm font-semibold mb-3" style={{ color }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function JsonList({ items }: { items: string[] }) {
  if (!items?.length) return <p className="text-xs text-[var(--text-muted)]">No data</p>;
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i} className="text-xs text-[var(--text-muted)]">
          &bull; {item}
        </li>
      ))}
    </ul>
  );
}

export default function DeepInsightsPanel({ result }: Props) {
  const has = (d: unknown) => d !== null && d !== undefined;
  const hasAnyBranch =
    has(result.brand_voice_data) ||
    has(result.audience_resonance_data) ||
    has(result.creative_variants_data) ||
    has(result.linguistic_data) ||
    has(result.gap_analysis_data) ||
    has(result.positioning_data) ||
    has(result.ab_test_data) ||
    has(result.roadmap_data);

  if (!hasAnyBranch) return null;

  const voice = result.brand_voice_data as Record<string, unknown> | null;
  const resonance = result.audience_resonance_data as Record<string, unknown> | null;
  const variants = result.creative_variants_data as Record<string, unknown> | null;
  const linguistic = result.linguistic_data as Record<string, unknown> | null;
  const gaps = result.gap_analysis_data as Record<string, unknown> | null;
  const positioning = result.positioning_data as Record<string, unknown> | null;
  const abTests = result.ab_test_data as Record<string, unknown> | null;
  const roadmap = result.roadmap_data as Record<string, unknown> | null;

  return (
    <div className="glass-card p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold">Deep Analysis Insights</h2>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Extended analysis from branch agents (deep mode)
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Brand Voice */}
        {voice && (
          <Section title="Brand Voice Profile" color="var(--accent-light)">
            {Boolean(voice.brand_profile) && (
              <div className="space-y-1 text-xs text-[var(--text-muted)]">
                <p>
                  <span className="font-medium text-[var(--foreground)]">Archetype:</span>{" "}
                  {String((voice.brand_profile as Record<string, unknown>).voice_archetype)}
                </p>
                <p>
                  <span className="font-medium text-[var(--foreground)]">Tone:</span>{" "}
                  {String((voice.brand_profile as Record<string, unknown>).tone)}
                </p>
                <p>
                  <span className="font-medium text-[var(--foreground)]">Strategy:</span>{" "}
                  {String((voice.brand_profile as Record<string, unknown>).messaging_strategy)}
                </p>
              </div>
            )}
            {Boolean(voice.voice_gap) && (
              <p className="mt-2 text-xs text-[var(--accent-light)]">
                Gap: {String(voice.voice_gap)}
              </p>
            )}
          </Section>
        )}

        {/* Audience Resonance */}
        {resonance && (
          <Section title="Audience Resonance" color="var(--score-high)">
            {Boolean(resonance.brand_resonance) && (
              <div className="space-y-1 text-xs text-[var(--text-muted)]">
                <p>
                  <span className="font-medium text-[var(--foreground)]">Score:</span>{" "}
                  {String((resonance.brand_resonance as Record<string, unknown>).resonance_score)}/10
                </p>
                <p>
                  <span className="font-medium text-[var(--foreground)]">Alignment:</span>{" "}
                  {String((resonance.brand_resonance as Record<string, unknown>).audience_alignment)}
                </p>
              </div>
            )}
            <JsonList items={(resonance.resonance_insights as string[]) || []} />
          </Section>
        )}

        {/* Creative Variants */}
        {variants && (variants.variants as unknown[])?.length > 0 && (
          <Section title="Creative Variants" color="#a78bfa">
            <div className="space-y-2">
              {(variants.variants as Array<Record<string, unknown>>).map((v, i) => (
                <div key={i} className="p-2 rounded-lg bg-[var(--background)]">
                  <p className="text-xs font-medium">&ldquo;{String(v.tagline)}&rdquo;</p>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">
                    {String(v.approach)} &middot; Est. {String(v.estimated_score)}/10
                  </p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Linguistic Analysis */}
        {linguistic && (
          <Section title="Linguistic Analysis" color="#f59e0b">
            {Boolean(linguistic.current_analysis) && (
              <div className="space-y-1 text-xs text-[var(--text-muted)]">
                <p>
                  Words: {String((linguistic.current_analysis as Record<string, unknown>).word_count)} &middot;
                  Syllables: {String((linguistic.current_analysis as Record<string, unknown>).syllable_count)} &middot;
                  Memorability: {String((linguistic.current_analysis as Record<string, unknown>).memorability_score)}/10
                </p>
              </div>
            )}
            <JsonList items={(linguistic.linguistic_recommendations as string[]) || []} />
          </Section>
        )}

        {/* Gap Analysis */}
        {gaps && (
          <Section title="Competitive Gaps" color="var(--score-low)">
            <JsonList items={(gaps.quick_wins as string[]) || []} />
            {(gaps.strategic_moats as string[])?.length > 0 && (
              <>
                <p className="text-xs font-medium text-[var(--score-high)] mt-2">
                  Strategic Moats:
                </p>
                <JsonList items={gaps.strategic_moats as string[]} />
              </>
            )}
          </Section>
        )}

        {/* Positioning */}
        {positioning && (
          <Section title="Competitive Positioning" color="#06b6d4">
            <JsonList items={(positioning.whitespace_opportunities as string[]) || []} />
            {Boolean(positioning.recommended_position) && (
              <p className="mt-2 text-xs text-[#06b6d4]">
                Recommended: {String(positioning.recommended_position)}
              </p>
            )}
          </Section>
        )}

        {/* A/B Tests */}
        {abTests && (abTests.ab_tests as unknown[])?.length > 0 && (
          <Section title="A/B Test Plans" color="#10b981">
            <div className="space-y-2">
              {(abTests.ab_tests as Array<Record<string, unknown>>).slice(0, 3).map((t, i) => (
                <div key={i} className="p-2 rounded-lg bg-[var(--background)]">
                  <p className="text-xs font-medium">{String(t.test_name)}</p>
                  <p className="text-xs text-[var(--text-muted)]">{String(t.hypothesis)}</p>
                  <p className="text-xs text-[#10b981]">Expected lift: {String(t.expected_lift)}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Roadmap */}
        {roadmap && (roadmap.phases as unknown[])?.length > 0 && (
          <Section title="Implementation Roadmap" color="#8b5cf6">
            <div className="space-y-2">
              {(roadmap.phases as Array<Record<string, unknown>>).map((p, i) => (
                <div key={i} className="p-2 rounded-lg bg-[var(--background)]">
                  <p className="text-xs font-medium">
                    Phase {String(p.phase)}: {String(p.name)} ({String(p.duration)})
                  </p>
                  <JsonList items={(p.actions as string[]) || []} />
                </div>
              ))}
            </div>
            {Boolean(roadmap.total_timeline) && (
              <p className="mt-2 text-xs text-[#8b5cf6]">
                Total: {String(roadmap.total_timeline)}
              </p>
            )}
          </Section>
        )}
      </div>
    </div>
  );
}
