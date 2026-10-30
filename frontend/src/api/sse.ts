/** Parsing of the server-sent event stream returned by `POST /conversations/{id}/messages`. */
import type { ChatEvent } from "./types";

/** Parse one SSE block ("data: {...}" lines) into an event, or null if it carries no data. */
export function parseBlock(block: string): ChatEvent | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  return data ? (JSON.parse(data) as ChatEvent) : null;
}

/** Yield chat events as they arrive on a streamed response body. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  // The cast works around a DOM lib typing mismatch (TextDecoderStream accepts Uint8Array chunks).
  const decoder = new TextDecoderStream() as unknown as ReadableWritablePair<string, Uint8Array>;
  const reader = body.pipeThrough(decoder).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = parseBlock(block);
      if (event) yield event;
    }
  }
  const last = parseBlock(buffer);
  if (last) yield last;
}
