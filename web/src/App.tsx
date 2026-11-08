import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  askQuestion,
  listDatasheets,
  type AskResponse,
  type Citation,
  type Datasheet,
} from "./api";
import { AskForm } from "./AskForm";
import { PageViewer, type PageMarking } from "./PageViewer";
import { Result } from "./Result";

export type View =
  | { kind: "idle" }
  | { kind: "loading"; question: string }
  | { kind: "answered"; response: AskResponse }
  | { kind: "failed"; question: string; message: string };

const QUESTION_PARAMETER = "q";

export function App() {
  const [question, setQuestion] = useState(questionFromUrl);
  const [view, setView] = useState<View>({ kind: "idle" });
  const [selected, setSelected] = useState(0);
  const [litNumber, setLitNumber] = useState<string | null>(null);
  const datasheets = useDatasheets();
  const latestRequest = useRef(0);

  async function submit(text: string) {
    const requestId = ++latestRequest.current;
    setQuestion(text);
    setView({ kind: "loading", question: text });
    setSelected(0);
    setLitNumber(null);
    writeQuestionToUrl(text);
    let next: View;
    try {
      next = { kind: "answered", response: await askQuestion(text) };
    } catch (error: unknown) {
      if (!(error instanceof ApiError)) throw error;
      next = { kind: "failed", question: text, message: error.message };
    }
    // A newer question replaces this one; its answer arrives too late to show.
    if (requestId === latestRequest.current) setView(next);
  }

  const shown = shownPage(view, selected);
  return (
    <>
      <header className="top">
        <span className="wordmark">Datasheet assistant</span>
        <CorpusLine datasheets={datasheets} />
      </header>
      <main className="app">
        <section className="ask-pane" aria-label="Question and answer">
          <AskForm
            question={question}
            onQuestionChange={setQuestion}
            onSubmit={(text) => void submit(text)}
            isBusy={view.kind === "loading"}
          />
          <Result
            view={view}
            datasheets={datasheets}
            selected={selected}
            onSelect={setSelected}
            onLight={setLitNumber}
            onAsk={(text) => void submit(text)}
          />
        </section>
        <section className="page-pane" aria-label="Datasheet page">
          <PageViewer view={view.kind} shown={shown} litNumber={litNumber} />
        </section>
      </main>
    </>
  );
}

function CorpusLine({ datasheets }: { datasheets: readonly Datasheet[] | null }) {
  if (datasheets === null) return null;
  const pageCount = datasheets.reduce((total, sheet) => total + sheet.page_count, 0);
  return (
    <span className="corpus">
      Answers from {datasheets.length} Bosch Sensortec datasheets, {pageCount} pages. Shown only
      when the quote and every number check out.
    </span>
  );
}

function shownPage(view: View, selected: number): PageMarking | null {
  if (view.kind !== "answered") return null;
  const { response } = view;
  switch (response.outcome) {
    case "verified":
      return viewable(response.answer.citations[selected], true);
    case "withheld":
      return viewable(response.drafts.at(-1)?.citations[0], false);
    case "unanswerable":
      return null;
  }
}

function viewable(citation: Citation | undefined, isVerified: boolean): PageMarking | null {
  if (citation?.page_count == null) return null;
  if (citation.page < 1 || citation.page > citation.page_count) return null;
  return { citation, pageCount: citation.page_count, isVerified };
}

function useDatasheets(): readonly Datasheet[] | null {
  const [datasheets, setDatasheets] = useState<readonly Datasheet[] | null>(null);
  useEffect(() => {
    // The list only decorates the page, so a failure leaves it out rather
    // than blocking questions.
    listDatasheets().then(setDatasheets, () => {
      setDatasheets(null);
    });
  }, []);
  return datasheets;
}

function questionFromUrl(): string {
  return new URLSearchParams(window.location.search).get(QUESTION_PARAMETER) ?? "";
}

function writeQuestionToUrl(question: string) {
  const url = new URL(window.location.href);
  url.searchParams.set(QUESTION_PARAMETER, question);
  window.history.replaceState(null, "", url);
}
