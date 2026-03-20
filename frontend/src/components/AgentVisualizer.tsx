"use client";

import { useState } from "react";
import type { AgentTrace, AgentNodeTrace } from "@/types";

interface Props {
  trace: AgentTrace;
}

// ── Layout & metadata for each node ─────────────────────────────
interface NodeLayout {
  label: string;
  x: number;
  y: number;
  description: string;
}

const NODE_META: Record<string, NodeLayout> = {
  depth_controller:        { label: "Depth Controller",        x: 400, y: 30,   description: "GPT-4o meta-agent — analyses brand input to auto-assign pipeline depth" },
  competitor_analysis:     { label: "Competitor Analysis",     x: 200, y: 120,  description: "Discovers and profiles competing brands via LLM research" },
  dimensions:              { label: "Dimensions",              x: 400, y: 120,  description: "Generates scoring dimensions tailored to category & audience" },
  memory:                  { label: "Memory",                  x: 600, y: 120,  description: "Retrieves brand guidelines and past feedback from memory" },
  trend_sentiment:         { label: "Trend & Sentiment",       x: 60,  y: 220,  description: "Google Trends + NewsAPI — market momentum & competitor tracking" },
  brand_voice_profiler:    { label: "Brand Voice",             x: 200, y: 220,  description: "Profiles voice archetype, tone, and messaging strategy" },
  audience_resonance:      { label: "Audience Resonance",      x: 340, y: 220,  description: "Maps audience alignment and emotional triggers" },
  benchmark:               { label: "Benchmark Generation",    x: 400, y: 320,  description: "Generates ideal benchmark tagline from competitor + trend context" },
  creative_variants:       { label: "Creative Variants",       x: 200, y: 420,  description: "Generates 4 alternative tagline approaches" },
  linguistic_analysis:     { label: "Linguistic Analysis",     x: 600, y: 420,  description: "Phonetics, rhythm, rhetorical devices & memorability scoring" },
  evaluator:               { label: "Evaluator Scoring",       x: 400, y: 420,  description: "Multi-dimensional scoring of brand vs competitors vs benchmark" },
  gap_analysis:            { label: "Gap Analysis",            x: 160, y: 520,  description: "Identifies score gaps, quick wins, and strategic moats" },
  competitive_positioning: { label: "Positioning Map",         x: 340, y: 520,  description: "Positioning map with whitespace opportunities" },
  trend_projection:        { label: "Trend Projection",       x: 520, y: 520,  description: "Historical score trajectory analysis & next-score prediction" },
  improvement:             { label: "Content Improvement",     x: 400, y: 620,  description: "Generates dimension-targeted improvement suggestions" },
  ab_test_generator:       { label: "A/B Test Plans",          x: 280, y: 720,  description: "Structured A/B test plans with hypotheses & expected lift" },
  implementation_roadmap:  { label: "Roadmap",                 x: 520, y: 720,  description: "Phased rollout plan with actions & timeline" },
};

// ── Edges — derived from parent field ────────────────────────────
interface Edge {
  from: string;
  to: string;
}

const EDGES: Edge[] = [
  { from: "START", to: "competitor_analysis" },
  { from: "START", to: "dimensions" },
  { from: "START", to: "memory" },
  { from: "competitor_analysis", to: "trend_sentiment" },
  { from: "competitor_analysis", to: "brand_voice_profiler" },
  { from: "competitor_analysis", to: "audience_resonance" },
  { from: "competitor_analysis", to: "benchmark" },
  { from: "trend_sentiment", to: "benchmark" },
  { from: "brand_voice_profiler", to: "benchmark" },
  { from: "audience_resonance", to: "benchmark" },
  { from: "dimensions", to: "benchmark" },
  { from: "memory", to: "benchmark" },
  { from: "benchmark", to: "evaluator" },
  { from: "benchmark", to: "creative_variants" },
  { from: "benchmark", to: "linguistic_analysis" },
  { from: "creative_variants", to: "evaluator" },
  { from: "linguistic_analysis", to: "evaluator" },
  { from: "evaluator", to: "improvement" },
  { from: "evaluator", to: "gap_analysis" },
  { from: "evaluator", to: "competitive_positioning" },
  { from: "evaluator", to: "trend_projection" },
  { from: "gap_analysis", to: "improvement" },
  { from: "competitive_positioning", to: "improvement" },
  { from: "trend_projection", to: "improvement" },
  { from: "improvement", to: "ab_test_generator" },
  { from: "improvement", to: "implementation_roadmap" },
  { from: "ab_test_generator", to: "END" },
  { from: "implementation_roadmap", to: "END" },
];

// START / END positions
const START_POS = { x: 400, y: 10 };
const END_POS = { x: 400, y: 800 };

// ── Helpers ──────────────────────────────────────────────────────
function getNodeColor(node: AgentNodeTrace): string {
  if (node.status === "skipped") return "var(--card-border)";
  if (node.role === "meta") return "#a78bfa";
  if (node.role === "core") return "var(--accent)";
  return "#06b6d4";
}

function formatDuration(ms: number): string {
  if (ms === 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const NODE_W = 140;
const NODE_H = 42;

export default function AgentVisualizer({ trace }: Props) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const nodeMap = new Map(trace.nodes.map((n) => [n.name, n]));

  // Build a set of completed node names for edge coloring
  const completedSet = new Set(
    trace.nodes.filter((n) => n.status === "completed").map((n) => n.name)
  );

  // Depth level badge color
  const depthColor =
    trace.depth_level === "deep"
      ? "#a78bfa"
      : trace.depth_level === "standard"
        ? "var(--accent)"
        : "var(--text-muted)";

  return (
    <div className="glass-card p-8">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div>
          <h2 className="text-lg font-semibold">Agent Pipeline Visualizer</h2>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            {trace.nodes_executed} agents executed &middot;{" "}
            {trace.nodes_skipped} skipped &middot;{" "}
            {formatDuration(trace.total_duration_ms)} total
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className="text-xs font-semibold px-3 py-1 rounded-full border"
            style={{ borderColor: depthColor, color: depthColor }}
          >
            {trace.depth_level.toUpperCase()} MODE
          </span>
          <svg
            className={`w-5 h-5 text-[var(--text-muted)] transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </div>

      {expanded && (
        <div className="mt-6">
          {/* Depth Controller Reasoning */}
          {trace.depth_reasoning && (
            <div className="mb-6 p-4 rounded-xl border border-[#a78bfa]/30 bg-[#a78bfa]/5">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold text-[#a78bfa]">
                  DEPTH CONTROLLER REASONING
                </span>
              </div>
              <p className="text-sm text-[var(--text-muted)]">
                {trace.depth_reasoning}
              </p>
              <div className="flex gap-4 mt-2 text-xs text-[var(--text-muted)]">
                <span>
                  Depth:{" "}
                  <strong style={{ color: depthColor }}>
                    {trace.depth_level}
                  </strong>
                </span>
                <span>
                  Trends:{" "}
                  <strong
                    style={{
                      color: trace.enable_trends
                        ? "var(--score-high)"
                        : "var(--score-low)",
                    }}
                  >
                    {trace.enable_trends ? "enabled" : "disabled"}
                  </strong>
                </span>
              </div>
            </div>
          )}

          {/* Legend */}
          <div className="flex flex-wrap gap-4 mb-4 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: "#a78bfa" }}
              />
              Meta Agent
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: "var(--accent)" }}
              />
              Core Agent
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: "#06b6d4" }}
              />
              Branch Agent
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-sm border border-[var(--card-border)]"
                style={{ background: "transparent" }}
              />
              Skipped
            </span>
          </div>

          {/* SVG Graph */}
          <div className="relative overflow-x-auto">
            <svg
              viewBox="0 0 800 830"
              className="w-full max-w-3xl mx-auto"
              style={{ minWidth: 600 }}
            >
              {/* Edges */}
              {EDGES.map((edge, i) => {
                const fromPos =
                  edge.from === "START"
                    ? START_POS
                    : NODE_META[edge.from]
                      ? {
                          x: NODE_META[edge.from].x,
                          y: NODE_META[edge.from].y + NODE_H / 2,
                        }
                      : null;
                const toPos =
                  edge.to === "END"
                    ? END_POS
                    : NODE_META[edge.to]
                      ? {
                          x: NODE_META[edge.to].x,
                          y: NODE_META[edge.to].y - NODE_H / 2,
                        }
                      : null;
                if (!fromPos || !toPos) return null;

                const fromCompleted =
                  edge.from === "START" || completedSet.has(edge.from);
                const toCompleted =
                  edge.to === "END" || completedSet.has(edge.to);
                const active = fromCompleted && toCompleted;

                return (
                  <line
                    key={i}
                    x1={fromPos.x}
                    y1={fromPos.y}
                    x2={toPos.x}
                    y2={toPos.y}
                    stroke={active ? "var(--accent)" : "var(--card-border)"}
                    strokeWidth={active ? 1.5 : 0.8}
                    strokeDasharray={active ? "" : "4 3"}
                    opacity={active ? 0.7 : 0.3}
                  />
                );
              })}

              {/* START node */}
              <circle
                cx={START_POS.x}
                cy={START_POS.y}
                r={6}
                fill="var(--score-high)"
              />

              {/* END node */}
              <circle cx={END_POS.x} cy={END_POS.y} r={6} fill="var(--score-high)" />
              <text
                x={END_POS.x}
                y={END_POS.y + 18}
                textAnchor="middle"
                className="text-[10px]"
                fill="var(--text-muted)"
              >
                END
              </text>

              {/* Agent nodes */}
              {Object.entries(NODE_META).map(([name, layout]) => {
                const node = nodeMap.get(name);
                if (!node) return null;
                const color = getNodeColor(node);
                const isHovered = hoveredNode === name;
                const isCompleted = node.status === "completed";

                return (
                  <g
                    key={name}
                    onMouseEnter={() => setHoveredNode(name)}
                    onMouseLeave={() => setHoveredNode(null)}
                    style={{ cursor: "pointer" }}
                  >
                    {/* Node rect */}
                    <rect
                      x={layout.x - NODE_W / 2}
                      y={layout.y - NODE_H / 2}
                      width={NODE_W}
                      height={NODE_H}
                      rx={8}
                      fill={
                        isCompleted
                          ? isHovered
                            ? `color-mix(in srgb, ${color} 20%, transparent)`
                            : `color-mix(in srgb, ${color} 10%, transparent)`
                          : "transparent"
                      }
                      stroke={color}
                      strokeWidth={isHovered ? 2 : 1}
                      strokeDasharray={isCompleted ? "" : "4 3"}
                      opacity={isCompleted ? 1 : 0.4}
                    />

                    {/* Label */}
                    <text
                      x={layout.x}
                      y={layout.y - 2}
                      textAnchor="middle"
                      className="text-[10px] font-medium"
                      fill={isCompleted ? "var(--foreground)" : "var(--text-muted)"}
                      opacity={isCompleted ? 1 : 0.5}
                    >
                      {layout.label}
                    </text>

                    {/* Duration label */}
                    {node.duration_ms > 0 && (
                      <text
                        x={layout.x}
                        y={layout.y + 12}
                        textAnchor="middle"
                        className="text-[8px]"
                        fill={color}
                      >
                        {formatDuration(node.duration_ms)}
                      </text>
                    )}

                    {/* Status dot */}
                    <circle
                      cx={layout.x + NODE_W / 2 - 8}
                      cy={layout.y - NODE_H / 2 + 8}
                      r={3}
                      fill={isCompleted ? "var(--score-high)" : "var(--card-border)"}
                    />
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Tooltip / detail panel */}
          {hoveredNode && NODE_META[hoveredNode] && (
            <div className="mt-4 p-4 rounded-xl border border-[var(--card-border)] bg-[var(--card-bg)]">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">
                  {NODE_META[hoveredNode].label}
                </h3>
                {nodeMap.get(hoveredNode) && (
                  <span
                    className="text-xs font-medium px-2 py-0.5 rounded-full"
                    style={{
                      color: getNodeColor(nodeMap.get(hoveredNode)!),
                      background: `color-mix(in srgb, ${getNodeColor(nodeMap.get(hoveredNode)!)} 15%, transparent)`,
                    }}
                  >
                    {nodeMap.get(hoveredNode)!.role} &middot;{" "}
                    {nodeMap.get(hoveredNode)!.status}
                  </span>
                )}
              </div>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                {NODE_META[hoveredNode].description}
              </p>
              {nodeMap.get(hoveredNode)?.duration_ms ? (
                <p className="text-xs text-[var(--accent-light)] mt-1">
                  Execution time: {formatDuration(nodeMap.get(hoveredNode)!.duration_ms)}
                </p>
              ) : null}
            </div>
          )}

          {/* Agent execution table */}
          <div className="mt-6">
            <h3 className="text-sm font-semibold mb-3">Execution Summary</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[var(--text-muted)] border-b border-[var(--card-border)]">
                    <th className="text-left py-2 pr-4">Agent</th>
                    <th className="text-left py-2 pr-4">Role</th>
                    <th className="text-left py-2 pr-4">Status</th>
                    <th className="text-right py-2">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {trace.nodes.map((node) => (
                    <tr
                      key={node.name}
                      className="border-b border-[var(--card-border)]/50"
                      style={{ opacity: node.status === "skipped" ? 0.4 : 1 }}
                    >
                      <td className="py-1.5 pr-4 font-medium">
                        {NODE_META[node.name]?.label ?? node.name}
                      </td>
                      <td className="py-1.5 pr-4">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{
                            color: getNodeColor(node),
                            background: `color-mix(in srgb, ${getNodeColor(node)} 15%, transparent)`,
                          }}
                        >
                          {node.role}
                        </span>
                      </td>
                      <td className="py-1.5 pr-4">
                        <span className="flex items-center gap-1">
                          <span
                            className="w-1.5 h-1.5 rounded-full"
                            style={{
                              background:
                                node.status === "completed"
                                  ? "var(--score-high)"
                                  : "var(--card-border)",
                            }}
                          />
                          {node.status}
                        </span>
                      </td>
                      <td className="py-1.5 text-right text-[var(--accent-light)]">
                        {formatDuration(node.duration_ms)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
