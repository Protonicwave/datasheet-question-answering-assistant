import type { Datasheet } from "./api";
import type { View } from "./App";
import { ErrorIcon, SearchIcon } from "./icons";
import { VerifiedResult, WithheldResult } from "./Answers";

const EXAMPLE_QUESTIONS = [
  "What is the maximum interface supply voltage VDDIO of the BMP390?",
  "What is the typical sleep current of the BME280?",
  "Which register sets the IIR filter coefficient on the BMP390?",
  "What value does the CHIP_ID register of the BMI270 return?",
];

interface ResultProps {
  view: View;
  datasheets: readonly Datasheet[] | null;
  selected: number;
  onSelect: (citation: number) => void;
  onLight: (value: string | null) => void;
  onAsk: (question: string) => void;
}

export function Result({ view, datasheets, selected, onSelect, onLight, onAsk }: ResultProps) {
  switch (view.kind) {
    case "idle":
      return <Welcome datasheets={datasheets} onAsk={onAsk} />;
    case "loading":
      return <Loading />;
    case "failed":
      return (
        <Failed
          message={view.message}
          onRetry={() => {
            onAsk(view.question);
          }}
        />
      );
    case "answered":
      break;
  }
  const { response } = view;
  switch (response.outcome) {
    case "verified":
      return (
        <VerifiedResult
          answer={response.answer}
          drafts={response.drafts}
          selected={selected}
          onSelect={onSelect}
          onLight={onLight}
        />
      );
    case "withheld":
      return <WithheldResult drafts={response.drafts} />;
    case "unanswerable":
      return <Unanswerable revised={response.drafts.length > 0} />;
  }
}

function Unanswerable({ revised }: { revised: boolean }) {
  return (
    <div className="result">
      <div className="status warn" role="status">
        <SearchIcon />
        <span>
          <strong>Searched the datasheets.</strong> The closest passages do not state it.
        </span>
      </div>
      <p className="answer refusal">The datasheet does not say.</p>
      {revised && (
        <p>A first answer failed the check, and the revision found no passage that states it.</p>
      )}
    </div>
  );
}

function Failed({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="result">
      <div className="status err" role="alert">
        <ErrorIcon />
        <span>
          <strong>No answer.</strong> {message}
        </span>
      </div>
      <p className="answer refusal">Nothing was answered or checked, so nothing is shown.</p>
      <p>
        <button className="btn secondary" type="button" onClick={onRetry}>
          Ask again
        </button>
      </p>
    </div>
  );
}

function Loading() {
  return (
    <div className="result loading" aria-busy="true">
      <div className="bar" role="progressbar" aria-label="Answering" />
      <p className="hint">
        Searching the datasheets, answering and checking the quotes. This usually takes 10 to 30
        seconds.
      </p>
      <div className="skeleton" aria-hidden="true">
        <span style={{ width: "92%" }} />
        <span style={{ width: "78%" }} />
        <span style={{ width: "40%" }} />
      </div>
    </div>
  );
}

function Welcome({
  datasheets,
  onAsk,
}: {
  datasheets: readonly Datasheet[] | null;
  onAsk: (question: string) => void;
}) {
  return (
    <div className="result">
      <div>
        <h2 className="sub">Try one of these</h2>
        <ul className="examples">
          {EXAMPLE_QUESTIONS.map((question) => (
            <li key={question}>
              <button
                type="button"
                onClick={() => {
                  onAsk(question);
                }}
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
      </div>
      {datasheets !== null && (
        <div>
          <h2 className="sub">Datasheets</h2>
          <dl className="sheets">
            {datasheets.map((sheet) => (
              <div key={sheet.name}>
                <dt>{sheet.name.toUpperCase()}</dt>
                <dd>{sheet.page_count} pages</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
