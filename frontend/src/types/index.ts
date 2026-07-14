// -- ListingIQ Core Types matching backend schemas --

export interface ListingInput {
  product_title: string;
  product_description: string;
  bullet_points: string[];
  brand_name: string;
  platform: "amazon" | "shopify" | "daraz" | "generic";
  target_audience: string;
}

// Agent 1: Input Parser
export interface ExtractedEntities {
  product_type: string;
  ingredients: string[];
  certifications: string[];
  dosage_info: string;
  target_audience: string;
  claims: string[];
  format_type: string;
}

export interface ParsedListing {
  original_title: string;
  original_description: string;
  original_bullets: string[];
  brand_name: string;
  platform: string;
  extracted_entities: ExtractedEntities;
}

// Agent 2: Category Classifier
export interface CategoryClassification {
  vertical: string;
  category: string;
  subcategory: string;
  confidence: number;
  reasoning: string;
}

export interface RubricDimension {
  name: string;
  weight: number;
  description: string;
  scoring_criteria: string;
}

export interface ScoringRubric {
  subcategory: string;
  dimensions: RubricDimension[];
  version: string;
}

// Agent 3: Competitor Scout
export interface CompetitorListing {
  rank: number;
  title: string;
  description: string;
  bullet_points: string[];
  brand_name: string;
  price: string;
  rating: number;
  review_count: number;
  badges: string[];
  url: string;
}

export interface CompetitorScoutResult {
  listings: CompetitorListing[];
  search_query: string;
  platform: string;
  data_source: string;
}

// Agent 4: Competitor Analyzer
export interface KeywordPattern {
  keyword: string;
  frequency: number;
  position: string;
}

export interface ClaimPattern {
  claim: string;
  frequency: number;
  example_brand: string;
}

export interface CompetitorAnalysis {
  keyword_patterns: KeywordPattern[];
  claim_patterns: ClaimPattern[];
  trust_signals: { signal: string; frequency: number }[];
  structural_patterns: Record<string, unknown>;
  differentiation_insights: string[];
  summary: string;
}

// Agent 5: Listing Analyzer
export interface DimensionExtraction {
  dimension_name: string;
  present: boolean;
  extracted_value: string;
  evidence: string;
  completeness: number;
}

export interface ListingAnalysis {
  dimensions: DimensionExtraction[];
  overall_completeness: number;
  missing_dimensions: string[];
  present_dimensions: string[];
}

// Agent 6: Benchmark Scorer
export interface DimensionScore {
  dimension: string;
  weight: number;
  score: number;
  explanation: string;
  competitor_avg: number;
  gap: number;
  strengths: string[];
  weaknesses: string[];
}

export interface ListingScore {
  overall_score: number;
  dimension_scores: DimensionScore[];
  percentile: number;
  gap_analysis: {
    dimension: string;
    score: number;
    competitor_avg: number;
    gap: number;
    weight: number;
    impact: number;
  }[];
}

// Agent 7: Recommendation Engine
export interface Recommendation {
  priority: number;
  dimension: string;
  current_score: number;
  projected_score: number;
  impact: "high" | "medium" | "low";
  specific_copy: string;
  competitive_evidence: string;
  expected_lift: string;
}

export interface RecommendationResult {
  recommendations: Recommendation[];
  quick_wins: Recommendation[];
  strategic_moves: Recommendation[];
}

// Agent 8: Rewrite Generator
export interface ListingRewrite {
  variant_name: string;
  strategy: string;
  title: string;
  bullet_points: string[];
  description: string;
  expected_score: number;
  key_changes: string[];
}

export interface RewriteResult {
  variants: ListingRewrite[];
  original_score: number;
  best_variant_score: number;
}

// Agent Trace
export interface AgentNodeTrace {
  name: string;
  role: string;
  status: "completed" | "skipped";
  duration_ms: number;
  parent: string;
}

export interface AgentTrace {
  total_duration_ms: number;
  nodes_executed: number;
  nodes_skipped: number;
  nodes: AgentNodeTrace[];
}

// Feedback
export interface FeedbackEntry {
  session_id: string;
  brand_name: string;
  feedback_type: "accepted" | "rejected" | "guideline";
  original_content: string;
  suggested_content?: string;
  user_comment?: string;
  dimension?: string;
}

export interface MemoryEntry {
  brand_name: string;
  guideline: string;
  source: string;
  confidence: number;
}

// Pipeline
export interface FullPipelineResponse {
  parsed_listing: ParsedListing;
  category: CategoryClassification;
  rubric: ScoringRubric;
  competitors: CompetitorScoutResult;
  competitor_analysis: CompetitorAnalysis;
  listing_analysis: ListingAnalysis;
  scores: ListingScore;
  recommendations: RecommendationResult;
  rewrites: RewriteResult;
  agent_trace?: AgentTrace | null;
}
