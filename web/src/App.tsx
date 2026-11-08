import { useEffect, useState } from "react";
import {
  ApiError,
  askQuestion,
  listDatasheets,
  MAX_QUESTION_CHARACTERS,
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
  async function submit(text: string) {
    setQuestion(text);
    setView({ kind: "loading", question: text });
    setSelected(0);
    setLitNumber(null);
    writeQuestionToUrl(text);
    // Every way to ask is disabled while loading, so no answer can arrive
    // after a newer question.
    try {
      setView({ kind: "answered", response: await askQuestion(text) });
    } catch (error: unknown) {
      if (!(error instanceof ApiError)) throw error;
      setView({ kind: "failed", question: text, message: error.message });
    }
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
      return firstViewable(response.drafts.at(-1)?.citations ?? []);
    case "unanswerable":
      return null;
  }
}

function firstViewable(citations: readonly Citation[]): PageMarking | null {
  for (const citation of citations) {
    const marking = viewable(citation, false);
    if (marking !== null) return marking;
  }
  return null;
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
  const question = new URLSearchParams(window.location.search).get(QUESTION_PARAMETER) ?? "";
  // The text box limits typing, not a value set from a link.
  return question.slice(0, MAX_QUESTION_CHARACTERS);
}

function writeQuestionToUrl(question: string) {
  const url = new URL(window.location.href);
  url.searchParams.set(QUESTION_PARAMETER, question);
  window.history.replaceState(null, "", url);
}
