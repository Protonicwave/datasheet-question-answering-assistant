import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const BOX = { left: 0.1, top: 0.4, right: 0.8, bottom: 0.42 };

function citation(page: number, quote: string, withNumber: boolean) {
  return {
    datasheet: "bme280",
    page,
    page_count: 60,
    quote,
    marks: { quote: [BOX], numbers: withNumber ? [{ value: "0.1", boxes: [BOX] }] : [] },
  };
}

const VERIFIED_ANSWER = {
  segments: [
    { text: "The sleep current is ", number: null },
    { text: "0.1", number: "0.1" },
    { text: " µA.", number: null },
  ],
  citations: [
    citation(2, "0.1 µA in sleep mode", true),
    citation(8, "Sleep current IDDSL 0.1 0.3 µA", true),
  ],
  rejection: null,
};

const REJECTED_DRAFT = {
  segments: [{ text: "It selects 10 ms.", number: null }],
  citations: [citation(26, "‘110’: 10 ms", false)],
  rejection: {
    reason: "quote_too_short",
    detail: "quote_too_short: bme280 page 26: quote has 3 words, expected at least 4",
  },
};

const DATASHEETS = [
  { name: "bme280", page_count: 60 },
  { name: "bmp390", page_count: 59 },
];

type Reply = { status: number; body: unknown } | "network-down";

let askReplies: Reply[] = [];
let askBodies: unknown[] = [];

function respond(reply: Reply): Response {
  if (reply === "network-down") throw new TypeError("Failed to fetch");
  return new Response(JSON.stringify(reply.body), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  askReplies = [];
  askBodies = [];
  window.history.replaceState(null, "", "/");
  vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
    if (url === "/api/datasheets") return Promise.resolve(respond({ status: 200, body: DATASHEETS }));
    if (url === "/api/ask") {
      askBodies.push(typeof init.body === "string" ? JSON.parse(init.body) : init.body);
      const reply = askReplies.shift();
      if (reply === undefined) return new Promise(() => undefined);
      return Promise.resolve().then(() => respond(reply));
    }
    throw new Error(`unexpected request to ${url}`);
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function ask(question: string, ...replies: Reply[]) {
  askReplies.push(...replies);
  const user = userEvent.setup();
  render(<App />);
  await user.type(screen.getByLabelText("Ask a datasheet"), question);
  await user.click(screen.getByRole("button", { name: "Ask" }));
  return user;
}

describe("first visit", () => {
  it("offers example questions and lists the datasheets", async () => {
    render(<App />);

    expect(screen.getByRole("button", { name: /sleep current of the BME280/ })).toBeTruthy();
    expect(await screen.findByText("BMP390")).toBeTruthy();
    expect(screen.getByText(/2 Bosch Sensortec datasheets, 119 pages/)).toBeTruthy();
  });

  it("asks an example question when it is chosen", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: /sleep current of the BME280/ }));

    expect(askBodies).toEqual([{ question: "What is the typical sleep current of the BME280?" }]);
  });

  it("takes the question from the address, cut to the limit", () => {
    window.history.replaceState(null, "", `/?q=${"x".repeat(600)}`);

    render(<App />);

    expect(screen.getByLabelText<HTMLTextAreaElement>("Ask a datasheet").value).toHaveLength(500);
  });

  it("cannot ask an empty question", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Ask" })).toHaveProperty("disabled", true);
  });
});

describe("asking", () => {
  it("sends the question on Enter but not on Shift and Enter", async () => {
    const user = userEvent.setup();
    render(<App />);
    const box = screen.getByLabelText("Ask a datasheet");

    await user.type(box, "Sleep current?{Shift>}{Enter}{/Shift}");
    expect(askBodies).toEqual([]);
    await user.type(box, "{Enter}");

    expect(askBodies).toEqual([{ question: "Sleep current?" }]);
  });

  it("shows progress and blocks a second question while answering", async () => {
    await ask("Sleep current?");

    expect(screen.getByRole("progressbar")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asking" })).toHaveProperty("disabled", true);
  });

  it("keeps the question in the address", async () => {
    await ask("Sleep current?");

    expect(new URLSearchParams(window.location.search).get("q")).toBe("Sleep current?");
  });
});

describe("a verified answer", () => {
  const verified = { status: 200, body: { outcome: "verified", answer: VERIFIED_ANSWER, drafts: [] } };

  it("shows the answer, its sources and the first cited page", async () => {
    await ask("Sleep current?", verified);

    expect(await screen.findByText("Verified.")).toBeTruthy();
    expect(screen.getByText("Sleep current IDDSL 0.1 0.3 µA")).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("src")).toBe("/api/pages/bme280/2.png");
  });

  it("switches the page when another source is chosen", async () => {
    const user = await ask("Sleep current?", verified);

    await user.click(await screen.findByRole("button", { name: /page 8/ }));

    expect(screen.getByRole("img").getAttribute("src")).toBe("/api/pages/bme280/8.png");
    expect(screen.getByRole("button", { name: /page 8/ }).getAttribute("aria-pressed")).toBe("true");
  });

  it("lights the number on the page while the answer's number is hovered", async () => {
    const user = await ask("Sleep current?", verified);
    const number = await screen.findByText("0.1", { selector: ".n" });

    await user.hover(number);
    expect(document.querySelectorAll(".number.lit")).toHaveLength(1);
    await user.unhover(number);

    expect(document.querySelectorAll(".number.lit")).toHaveLength(0);
  });

  it("says when it passed only after a revision", async () => {
    await ask("Standby time?", {
      status: 200,
      body: { outcome: "verified", answer: VERIFIED_ANSWER, drafts: [REJECTED_DRAFT] },
    });

    expect(await screen.findByText("Verified after a revision.")).toBeTruthy();
    expect(screen.getByText("Its quote was shorter than four words.")).toBeTruthy();
  });
});

describe("a withheld answer", () => {
  it("shows no answer, the reason and the cited page outlined", async () => {
    await ask("Standby time?", {
      status: 200,
      body: { outcome: "withheld", answer: null, drafts: [REJECTED_DRAFT, REJECTED_DRAFT] },
    });

    expect(await screen.findByText("No verified answer.")).toBeTruthy();
    expect(screen.getByText(/failed the check 2 times/)).toBeTruthy();
    expect(screen.getByText(/dashed outline marks what it quoted/)).toBeTruthy();
    expect(document.querySelectorAll(".mark.unverified")).toHaveLength(1);
    expect(document.querySelectorAll(".number")).toHaveLength(0);
  });
});

describe("a withheld answer citing a missing page first", () => {
  it("shows the first cited page that exists", async () => {
    const missingFirst = {
      ...REJECTED_DRAFT,
      citations: [{ ...citation(99, "beyond the end", false), marks: null }, citation(26, "‘110’: 10 ms", false)],
    };

    await ask("Standby time?", {
      status: 200,
      body: { outcome: "withheld", answer: null, drafts: [missingFirst] },
    });

    expect((await screen.findByRole("img")).getAttribute("src")).toBe("/api/pages/bme280/26.png");
  });

  it("shows a rejection reason it does not know by its detail", async () => {
    const unknownReason = { ...REJECTED_DRAFT, rejection: { reason: "new_rule", detail: "a new rule failed" } };

    await ask("Standby time?", {
      status: 200,
      body: { outcome: "withheld", answer: null, drafts: [unknownReason] },
    });

    expect(await screen.findByText("a new rule failed")).toBeTruthy();
  });
});

describe("an unanswerable question", () => {
  it("says the datasheet does not say and shows no page", async () => {
    await ask("Thermal resistance?", {
      status: 200,
      body: { outcome: "unanswerable", answer: null, drafts: [] },
    });

    expect(await screen.findByText("The datasheet does not say.")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("a failed request", () => {
  it("shows the server's reason and asks again on request", async () => {
    const user = await ask(
      "Sleep current?",
      { status: 502, body: { detail: "Claude API request failed: overloaded" } },
      { status: 200, body: { outcome: "unanswerable", answer: null, drafts: [] } },
    );

    expect(await screen.findByText(/request failed: overloaded/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Ask again" }));

    expect(await screen.findByText("The datasheet does not say.")).toBeTruthy();
    expect(askBodies).toHaveLength(2);
  });

  it("says when the server cannot be reached", async () => {
    await ask("Sleep current?", "network-down");

    expect(await screen.findByText(/Could not reach the server/)).toBeTruthy();
  });

  it("treats a reply of the wrong shape as a failure", async () => {
    await ask("Sleep current?", { status: 200, body: { outcome: "verified" } });

    await waitFor(() => {
      expect(screen.getByText(/not in the expected form/)).toBeTruthy();
    });
  });
});
