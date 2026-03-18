"use client";

import {
  Radar,
  RadarChart as RechartsRadar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Legend,
} from "recharts";
import type { EvaluationResult } from "@/types";

interface Props {
  evaluation: EvaluationResult;
}

const COLORS = ["#dc2626", "#2563eb", "#d97706", "#16a34a", "#9333ea"];

export default function RadarChartComponent({ evaluation }: Props) {
  const { user_score, competitor_scores, dimensions } = evaluation;
  const allScores = [user_score, ...competitor_scores];

  const chartData = dimensions.map((dim) => {
    const entry: Record<string, string | number> = { dimension: dim.name };
    allScores.forEach((s) => {
      const ds = s.dimension_scores.find((d) => d.dimension === dim.name);
      entry[s.brand_name] = ds?.score ?? 0;
    });
    entry["Benchmark"] = 10;
    return entry;
  });

  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-4">Competitive Radar</h2>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsRadar cx="50%" cy="50%" outerRadius="75%" data={chartData}>
            <PolarGrid stroke="rgba(0,0,0,0.1)" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: "#6b7280", fontSize: 11 }}
            />
            <PolarRadiusAxis
              angle={30}
              domain={[0, 10]}
              tick={{ fill: "#6b7280", fontSize: 10 }}
              tickCount={6}
            />
            {allScores.map((s, i) => (
              <Radar
                key={s.brand_name}
                name={s.brand_name}
                dataKey={s.brand_name}
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={
                  s.brand_name === user_score.brand_name ? 0.2 : 0.05
                }
                strokeWidth={
                  s.brand_name === user_score.brand_name ? 2.5 : 1.5
                }
              />
            ))}
            <Radar
              name="Benchmark"
              dataKey="Benchmark"
              stroke="rgba(0,0,0,0.1)"
              fill="transparent"
              strokeWidth={1}
              strokeDasharray="4 4"
            />
            <Legend wrapperStyle={{ fontSize: 12, color: "#6b7280" }} />
          </RechartsRadar>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
