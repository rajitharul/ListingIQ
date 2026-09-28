// -- ListingIQ Core Types matching backend schemas --

/** Platform slugs the backend registry knows. "auto" = detect from the URL. */
export type Platform =
  | "auto" | "amazon" | "walmart" | "ebay" | "etsy" | "target"
  | "shopify" | "dtc" | "generic";

export const PLATFORM_LABELS: Record<string, string> = {
  auto: "Detect automatically",
  amazon: "Amazon",
  walmart: "Walmart",
  ebay: "eBay",
  etsy: "Etsy",
  target: "Target",
  iherb: "iHerb",
  aliexpress: "AliExpress",
  daraz: "Daraz",
  noon: "Noon",
  bestbuy: "Best Buy",
  shopify: "Shopify store",
  dtc: "Brand site",
  generic: "Other",
};

export function platformLabel(slug: string | undefined): string {
  if (!slug) return "Unknown";
  return PLATFORM_LABELS[slug] ?? slug;
}

export interface ListingInput {
  product_title: string;
  product_description: string;
  bullet_points: string[];
  brand_name: string;
  platform: Platform;
  target_audience: string;
  /** Optional: the listing's own URL, used to prefill the fields above. */
  listing_url?: string;
}

/** Where the user's own listing came from, when it was read from a URL. */
export interface OwnListingSource {
  url: string;
  platform_detected: string;
  /** extracted | failed | none */
  status: string;
  note: string;
  fetched_at: string;
  fields_filled: string[];
}

export interface ExtractListingResponse {
  listing: ListingInput;
  source: OwnListingSource;
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
  /** Per-listing provenance — a competitor set can span several platforms. */
  platform?: string;
  merchant?: string;
  domain?: string;
  source_position?: number;
  /** extracted | discovery_only | failed | none */
  extraction_status?: string;
  extraction_note?: string;
  /** False when the page had too little real copy to be scored fairly. */
  counts_toward_benchmark?: boolean;
}

/**
 * Sources that represent something actually observed. Mirrors
 * LIVE_DATA_SOURCES in backend/models/schemas.py — an allowlist, so a source
 * that is not named here is treated as an estimate rather than inheriting the
 * "observed data" treatment by default.
 */
export const LIVE_DATA_SOURCES = ["rainforest_api", "web_search"] as const;

export function isLiveData(dataSource: string | undefined): boolean {
  return (LIVE_DATA_SOURCES as readonly string[]).includes(dataSource ?? "");
}

export interface CompetitorScoutResult {
  listings: CompetitorListing[];
  search_query: string;
  platform: string;
  /** "rainforest_api" / "web_search" = observed; "llm_knowledge" = AI estimate. */
  data_source: string;
  fetched_at?: string;
  from_cache?: boolean;
  /** Why this source was used — e.g. the reason a live provider was unavailable. */
  provider_note?: string;
  /** platform slug -> count; sums to listings.length. */
  platform_breakdown?: Record<string, number>;
  queries?: string[];
  discovery_source?: string;
  extraction_source?: string;
  extracted_count?: number;
  discovery_only_count?: number;
  failed_count?: number;
}

// Competitor Scorer — the measured benchmark
export interface CompetitorDimensionStat {
  dimension: string;
  /** Real arithmetic mean of the competitors' scores, not an estimate. */
  mean: number;
  best: number;
  worst: number;
  n: number;
}

export interface CompetitorScoreRow {
  rank: number;
  brand_name: string;
  title: string;
  platform?: string;
  overall_score: number;
  dimension_scores: Record<string, number>;
}

export interface CompetitorBenchmark {
  dimensions: CompetitorDimensionStat[];
  competitors: CompetitorScoreRow[];
  overall_mean: number;
  rubric_version: string;
  from_cache: boolean;
  /** same_platform | all_competitors */
  cohort?: string;
  platforms?: string[];
  data_source?: string;
  is_live_data?: boolean;
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
  /**
   * Which cohort the headline percentile describes, and how big it was.
   * "top 18% of 11 Amazon sellers" can be checked; a bare percentile cannot.
   */
  percentile_basis?: "same_platform" | "all_competitors" | string;
  percentile_cohort_n?: number;
  /** Percentile against every competitor found, across platforms. */
  category_percentile?: number;
  category_cohort_n?: number;
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
  /** The generator's own projection — kept for comparison, not authoritative. */
  expected_score: number;
  key_changes: string[];
  /** Measured by re-scoring the variant. Only meaningful when is_verified. */
  measured_score: number;
  measured_percentile: number;
  measured_category_percentile?: number;
  measured_dimension_scores: Record<string, number>;
  is_verified: boolean;
}

export interface RewriteResult {
  variants: ListingRewrite[];
  original_score: number;
  /** Best MEASURED score once verified; the projection before that. */
  best_variant_score: number;
  scores_verified: boolean;
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
  competitor_benchmark: CompetitorBenchmark;
  /** Every competitor found, across platforms — context for the headline. */
  competitor_benchmark_all?: CompetitorBenchmark;
  listing_analysis: ListingAnalysis;
  scores: ListingScore;
  recommendations: RecommendationResult;
  rewrites: RewriteResult;
  agent_trace?: AgentTrace | null;
}

// ── Accounts & auth ──────────────────────────────────────────────

export interface UsageToday {
  day: string;
  tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  runs: number;
}

/** The signed-in caller, from GET /api/auth/me. */
export interface CurrentUser {
  account_id: string;
  email: string;
  role: "admin" | "member" | string;
  via: "session" | "api_key" | "auth-disabled" | string;
  rpm_limit: number;
  max_concurrent: number;
  daily_token_limit: number;
  usage_today: UsageToday;
  tokens_remaining: number;
}

/** An account row in the admin panel, from GET /api/admin/accounts. */
export interface AdminAccount {
  account_id: string;
  email: string;
  role: "admin" | "member" | string;
  active: boolean;
  rpm_limit: number;
  max_concurrent: number;
  daily_token_limit: number;
  created_at: string;
  last_login_at: string | null;
  usage_today: UsageToday;
}
