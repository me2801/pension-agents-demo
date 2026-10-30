import { parseBlock, readEvents } from "./sse";
import type { ChatEvent } from "./types";

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(chunks: string[]): Promise<ChatEvent[]> {
  const events: ChatEvent[] = [];
  for await (const event of readEvents(streamOf(chunks))) events.push(event);
  return events;
}

describe("parseBlock", () => {
  it("parses a data line", () => {
    expect(parseBlock('data: {"type":"step","text":"hi"}')).toEqual({ type: "step", text: "hi" });
  });

  it("ignores blocks without data", () => {
    expect(parseBlock(": keep-alive")).toBeNull();
  });
});

describe("readEvents", () => {
  it("yields events even when chunks split them", async () => {
    const events = await collect(['data: {"type":"step","te', 'xt":"a"}\n\ndata: {"type":"step",', '"text":"b"}\n\n']);
    expect(events).toEqual([
      { type: "step", text: "a" },
      { type: "step", text: "b" },
    ]);
  });

  it("yields a final event without trailing blank line", async () => {
    expect(await collect(['data: {"type":"step","text":"last"}'])).toEqual([{ type: "step", text: "last" }]);
  });
});
