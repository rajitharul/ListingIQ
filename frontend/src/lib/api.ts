import type {
  BrandInput,
  FullPipelineResponse,
  ImprovementSuggestion,
  FeedbackEntry,
  EvaluationResult,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API Error ${res.status}: ${err}`);
  }
  return res.json();
}

export async function runPipeline(
  brandInput: BrandInput
): Promise<FullPipelineResponse> {
  return apiFetch<FullPipelineResponse>("/api/pipeline", {
    method: "POST",
    body: JSON.stringify({
      brand_input: brandInput,
      session_id: `session_${Date.now()}`,
    }),
  });
}

export async function getImprovement(
  brandInput: BrandInput,
  targetDimension: string,
  currentEvaluation: EvaluationResult
): Promise<ImprovementSuggestion[]> {
  return apiFetch<ImprovementSuggestion[]>("/api/improve", {
    method: "POST",
    body: JSON.stringify({
      brand_input: brandInput,
      target_dimension: targetDimension,
      current_evaluation: currentEvaluation,
    }),
  });
}

export async function submitFeedback(
  entry: FeedbackEntry
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(entry),
  });
}

export async function addGuideline(
  brandName: string,
  guideline: string
): Promise<unknown> {
  return apiFetch(
    `/api/memory/guideline?brand_name=${encodeURIComponent(brandName)}&guideline=${encodeURIComponent(guideline)}`,
    { method: "POST" }
  );
}

/**
 * Stream the pipeline via SSE. Calls onNodeComplete for each finished node,
 * then resolves with the full FullPipelineResponse.
 */
export function runPipelineStream(
  brandInput: BrandInput,
  onNodeComplete: (node: string) => void
): Promise<FullPipelineResponse> {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({
      brand_input: brandInput,
      session_id: `session_${Date.now()}`,
    });

    fetch(`${API_BASE}/api/pipeline/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    })
      .then((res) => {
        if (!res.ok) {
          return res.text().then((t) => {
            throw new Error(`API Error ${res.status}: ${t}`);
          });
        }
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No readable stream");

        const decoder = new TextDecoder();
        let buffer = "";

        let settled = false;

        function processEvents(): void {
          // SSE protocol: events separated by double newline
          // Normalize \r\n → \n so split works with HTTP-style line endings
          buffer = buffer.replace(/\r\n/g, "\n");
          const parts = buffer.split("\n\n");
          buffer = parts.pop() || "";

          for (const part of parts) {
            if (settled) return;
            const lines = part.split("\n");
            let eventType = "";
            let data = "";
            for (const line of lines) {
              if (line.startsWith("event: ")) eventType = line.slice(7).trim();
              if (line.startsWith("data: ")) data += line.slice(6);
            }

            if (eventType === "node_complete" && data) {
              try {
                const payload = JSON.parse(data);
                onNodeComplete(payload.node);
              } catch {}
            } else if (eventType === "result" && data) {
              settled = true;
              try {
                resolve(JSON.parse(data) as FullPipelineResponse);
              } catch (e) {
                reject(new Error("Failed to parse result"));
              }
              return;
            } else if (eventType === "error" && data) {
              settled = true;
              try {
                const err = JSON.parse(data);
                reject(new Error(err.detail || "Pipeline error"));
              } catch {
                reject(new Error(data));
              }
              return;
            }
          }
        }

        function pump(): Promise<void> {
          return reader!.read().then(({ done, value }) => {
            if (value) {
              buffer += decoder.decode(value, { stream: !done });
            }
            processEvents();
            if (settled) return;
            if (done) {
              // Flush any remaining buffer as a final event
              if (buffer.trim()) {
                buffer += "\n\n";
                processEvents();
              }
              if (!settled) {
                reject(new Error("Stream ended without result"));
              }
              return;
            }
            return pump();
          });
        }

        pump().catch((e) => { if (!settled) reject(e); });
      })
      .catch(reject);
  });
}
