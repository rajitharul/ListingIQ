"use client";

import { useState } from "react";
import type { AgentTrace, AgentNodeTrace } from "@/types";

interface Props {
  trace: AgentTrace;
}

interface NodeLayout {
  label: string;
  x: number;
  y: number;
  description: string;
}

const NODE_META: Record<string, NodeLayout> = {
  input_parser:          { label: "Input Parser",          x: 400, y: 60,   description: "Extracts entities, ingredients, certifications, and claims from your listing" },
  category_classifier:   { label: "Category Classifier",   x: 400, y: 150,  description: "Identifies product vertical and subcategory, loads scoring rubric" },
  competitor_scout:      { label: "Competitor Scout",      x: 400, y: 240,  description: "Finds real competitors across platforms and reads their pages" },
  competitor_analyzer:   { label: "Competitor Analyzer",   x: 400, y: 330,  description: "Extracts keyword patterns, claim frequency, trust signals from competitors" },
  competitor_scorer:     { label: "Competitor Scorer",     x: 400, y: 420,  description: "Scores every fetched competitor on the same rubric, so the benchmark is measured rather than estimated" },
  listing_analyzer:      { label: "Listing Analyzer",      x: 400, y: 500,  description: "Evaluates your listing per rubric dimension — present/missing, evidence, completeness" },
  benchmark_scorer:      { label: "Benchmark Scorer",      x: 400, y: 580,  description: "Scores your listing 0-10 per dimension against competitor benchmarks" },
  recommendation_engine: { label: "Recommendation Engine", x: 400, y: 660,  description: "Generates prioritized recommendations with specific copy and competitive evidence" },
  rewrite_generator:     { label: "Rewrite Generator",     x: 400, y: 740,  description: "Creates 3 optimized rewrite variants — keyword, benefit-led, trust-forward" },
  rewrite_verifier:      { label: "Rewrite Verifier",      x: 400, y: 820,  description: "Re-scores each variant through the same scorer used on competitors, so its score is measured rather than self-reported" },
};

interface Edge {
  from: string;
  to: string;
}

const EDGES: Edge[] = [
  { from: "START", to: "input_parser" },
  { from: "input_parser", to: "category_classifier" },
  { from: "category_classifier", to: "competitor_scout" },
  { from: "competitor_scout", to: "competitor_analyzer" },
  { from: "competitor_analyzer", to: "competitor_scorer" },
  { from: "competitor_scorer", to: "listing_analyzer" },
  { from: "listing_analyzer", to: "benchmark_scorer" },
  { from: "benchmark_scorer", to: "recommendation_engine" },
  { from: "recommendation_engine", to: "rewrite_generator" },
  { from: "rewrite_generator", to: "rewrite_verifier" },
  { from: "rewrite_verifier", to: "END" },
];

const START_POS = { x: 400, y: 15 };
const END_POS = { x: 400, y: 880 };

function getNodeColor(node: AgentNodeTrace): string {
  if (node.status === "skipped") return "var(--card-border)";
  return "var(--accent)";
}

function formatDuration(ms: number): string {
  if (ms === 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

const NODE_W = 160;
const NODE_H = 42;

export default function AgentVisualizer({ trace }: Props) {
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const nodeMap = new Map(trace.nodes.map((n) => [n.name, n]));
  const completedSet = new Set(
    trace.nodes.filter((n) => n.status === "completed").map((n) => n.name)
  );

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

      {expanded && (
        <div className="mt-6">
          {/* Legend */}
          <div className="flex flex-wrap gap-4 mb-4 text-xs text-[var(--text-muted)]">
            <span className="flex items-center gap-1.5">
              <span
                className="w-3 h-3 rounded-full"
                style={{ background: "var(--accent)" }}
              />
              Completed
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
              viewBox="0 0 800 920"
              className="w-full max-w-3xl mx-auto"
              style={{ minWidth: 500 }}
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
