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
import type { ListingScore } from "@/types";

interface Props {
  scores: ListingScore;
}

export default function RadarChartComponent({ scores }: Props) {
  const chartData = scores.dimension_scores.map((dim) => ({
    dimension: dim.dimension.length > 18
      ? dim.dimension.slice(0, 16) + "..."
      : dim.dimension,
    "Your Listing": dim.score,
    "Competitor avg": dim.competitor_avg,
    Benchmark: 10,
  }));

  return (
    <div className="glass-card p-8">
      <h2 className="text-lg font-semibold mb-4">Competitive Radar</h2>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <RechartsRadar cx="50%" cy="50%" outerRadius="75%" data={chartData}>
            <PolarGrid stroke="rgba(0,0,0,0.1)" />
            <PolarAngleAxis
              dataKey="dimension"
              tick={{ fill: "#6b7280", fontSize: 10 }}
            />
            <PolarRadiusAxis
              angle={30}
              domain={[0, 10]}
              tick={{ fill: "#6b7280", fontSize: 10 }}
              tickCount={6}
            />
            <Radar
              name="Your Listing"
              dataKey="Your Listing"
              stroke="#059669"
              fill="#059669"
              fillOpacity={0.2}
              strokeWidth={2.5}
            />
            <Radar
              name="Competitor avg"
              dataKey="Competitor avg"
              stroke="#2563eb"
              fill="#2563eb"
              fillOpacity={0.05}
              strokeWidth={1.5}
            />
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
