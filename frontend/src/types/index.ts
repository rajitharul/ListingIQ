// -- Core Types matching backend schemas --

export interface BrandInput {
  brand_name: string;
  product_category: string;
  current_tagline: string;
  current_description: string;
  target_audience: string;
}

export interface Competitor {
  name: string;
  product: string;
  tagline: string;
  description: string;
  market_position: string;
}

export interface Dimension {
  name: string;
  description: string;
  weight: number;
}

export interface DimensionScore {
  dimension: string;
  score: number;
  explanation: string;
  strengths: string[];
  weaknesses: string[];
}

export interface ContentScore {
  brand_name: string;
  tagline: string;
  dimension_scores: DimensionScore[];
  overall_score: number;
  rank: number;
}

export interface BenchmarkSnippet {
  ideal_tagline: string;
  ideal_description: string;
  rationale: string;
  dimension_scores: DimensionScore[];
}

export interface ImprovementSuggestion {
  target_dimension: string;
  current_score: number;
  projected_score: number;
  original_text: string;
  improved_text: string;
  changes_made: string[];
  trade_offs: string[];
}

export interface CompetitorAnalysisResult {
  competitors: Competitor[];
  market_summary: string;
}

export interface EvaluationResult {
  user_score: ContentScore;
  competitor_scores: ContentScore[];
  benchmark: BenchmarkSnippet;
  dimensions: Dimension[];
  rankings: { brand: string; score: number; rank: number }[];
  insights: string[];
}

export interface FullPipelineResponse {
  competitors: CompetitorAnalysisResult;
  evaluation: EvaluationResult;
  suggestions: ImprovementSuggestion[];
  memory_context: {
    brand_name: string;
    guideline: string;
    source: string;
    confidence: number;
  }[];
}

export interface FeedbackEntry {
  session_id: string;
  brand_name: string;
  feedback_type: "accepted" | "rejected" | "guideline";
  original_content: string;
  suggested_content?: string;
  user_comment?: string;
  dimension?: string;
}
