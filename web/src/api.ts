import { z } from "zod";

// The API retries a failed model request and may revise a rejected answer
// once, so a slow answer can take several minutes before it fails.
const ASK_TIMEOUT_MS = 300_000;
const DATASHEETS_TIMEOUT_MS = 10_000;
// Matches MAX_QUESTION_CHARACTERS in server.py; a Python test checks this line.
export const MAX_QUESTION_CHARACTERS = 500;

const BoxSchema = z.object({
  left: z.number(),
  top: z.number(),
  right: z.number(),
  bottom: z.number(),
});

const CitationSchema = z.object({
  datasheet: z.string(),
  page: z.number().int(),
  page_count: z.number().int().nullable(),
  quote: z.string(),
  marks: z
    .object({
      quote: z.array(BoxSchema),
      numbers: z.array(z.object({ value: z.string(), boxes: z.array(BoxSchema) })),
    })
    .nullable(),
});


const DraftSchema = z.object({
  segments: z.array(z.object({ text: z.string(), number: z.string().nullable() })),
  citations: z.array(CitationSchema),
  // A reason added to the check later is still shown, by its detail alone.
  rejection: z.object({ reason: z.string(), detail: z.string() }).nullable(),
});

const AskResponseSchema = z.discriminatedUnion("outcome", [
  z.object({ outcome: z.literal("verified"), answer: DraftSchema, drafts: z.array(DraftSchema) }),
  z.object({ outcome: z.literal("withheld"), answer: z.null(), drafts: z.array(DraftSchema).min(1) }),
  z.object({ outcome: z.literal("unanswerable"), answer: z.null(), drafts: z.array(DraftSchema) }),
]);

const DatasheetsSchema = z.array(z.object({ name: z.string(), page_count: z.number().int() }));

export type Box = z.infer<typeof BoxSchema>;
export type Citation = z.infer<typeof CitationSchema>;
export type Draft = z.infer<typeof DraftSchema>;
export type AskResponse = z.infer<typeof AskResponseSchema>;
export type Datasheet = z.infer<typeof DatasheetsSchema>[number];

export class ApiError extends Error {
  override name = "ApiError";
}

export async function askQuestion(question: string): Promise<AskResponse> {
  const response = await request("/api/ask", ASK_TIMEOUT_MS, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  return parseReply(AskResponseSchema, response);
}

export async function listDatasheets(): Promise<Datasheet[]> {
  const response = await request("/api/datasheets", DATASHEETS_TIMEOUT_MS, {});
  return parseReply(DatasheetsSchema, response);
}

export function pageImageUrl(datasheet: string, page: number): string {
  return `/api/pages/${encodeURIComponent(datasheet)}/${String(page)}.png`;
}

async function request(path: string, timeoutMs: number, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, signal: AbortSignal.timeout(timeoutMs) });
  } catch (error: unknown) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(`No reply after ${String(timeoutMs / 1000)} seconds.`, { cause: error });
    }
    throw new ApiError("Could not reach the server. Is `datasheet-assistant serve` running?", {
      cause: error,
    });
  }
  if (!response.ok) {
    throw new ApiError(await errorDetail(response));
  }
  return response;
}

async function parseReply<T>(schema: z.ZodType<T>, response: Response): Promise<T> {
  const parsed = schema.safeParse(await response.json().catch(() => null));
  if (!parsed.success) {
    throw new ApiError("The server's reply was not in the expected form.", { cause: parsed.error });
  }
  return parsed.data;
}

async function errorDetail(response: Response): Promise<string> {
  const fallback = `The server answered ${String(response.status)} ${response.statusText}.`;
  // A body that is not JSON parses as null and falls back to the status.
  const parsed = z
    .object({ detail: z.string() })
    .safeParse(await response.json().catch(() => null));
  return parsed.success ? parsed.data.detail : fallback;
}
