import type { Citation, Draft } from "./api";
import { FailIcon, PassIcon, VerifiedIcon, WarningIcon } from "./icons";

const REJECTION_SENTENCES: ReadonlyMap<string, string> = new Map([
  ["no_citations", "It cited no passage."],
  ["unknown_datasheet", "It cited a datasheet that is not in the set."],
  ["page_out_of_range", "It cited a page the datasheet does not have."],
  ["quote_too_short", "Its quote was shorter than four words."],
  ["quote_not_on_page", "Its quote does not appear on the cited page."],
  ["number_not_in_quotes", "It stated a number that none of its quotes contains."],
]);

interface VerifiedResultProps {
  answer: Draft;
  drafts: readonly Draft[];
  selected: number;
  onSelect: (citation: number) => void;
  onLight: (value: string | null) => void;
}

export function VerifiedResult({ answer, drafts, selected, onSelect, onLight }: VerifiedResultProps) {
  return (
    <div className="result" aria-live="polite">
      <div className="status ok" role="status">
        <VerifiedIcon />
        <span>
          <strong>{drafts.length === 0 ? "Verified." : "Verified after a revision."}</strong>{" "}
          Every quote is on its cited page, and every number in the answer appears in a quote.
        </span>
      </div>
      <AnswerText draft={answer} onLight={onLight} />
      <div>
        <h2 className="sub">Sources</h2>
        <ul className="cites">
          {answer.citations.map((citation, position) => (
            <li key={`${citation.datasheet}-${String(citation.page)}-${String(position)}`}>
              <button
                className="cite"
                type="button"
                aria-pressed={position === selected}
                onClick={() => {
                  onSelect(position);
                }}
              >
                <span className="where">{location(citation)}</span>
                <span className="quote">
                  <mark>{citation.quote}</mark>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
      {drafts.length === 0 ? <HowChecked /> : <Drafts drafts={drafts} summary="Why the first answer was rejected" open />}
    </div>
  );
}

export function WithheldResult({ drafts }: { drafts: readonly Draft[] }) {
  return (
    <div className="result" aria-live="polite">
      <div className="status warn" role="status">
        <WarningIcon />
        <span>
          <strong>Withheld.</strong> The answer failed the check{" "}
          {drafts.length === 1 ? "once" : `${String(drafts.length)} times`}, so it is not shown as
          an answer.
        </span>
      </div>
      <p className="answer refusal">No verified answer.</p>
      <p>
        The datasheet may still state it. Where the last draft cited a real page, it is shown with
        the passage outlined; read the value there yourself.
      </p>
      <Drafts drafts={drafts} summary="Show the rejected drafts" open={false} />
    </div>
  );
}

function AnswerText({ draft, onLight }: { draft: Draft; onLight: (value: string | null) => void }) {
  return (
    <p className="answer">
      {draft.segments.map((segment, position) => {
        const key = String(position);
        if (segment.number === null) return <span key={key}>{segment.text}</span>;
        const value = segment.number;
        const light = () => {
          onLight(value);
        };
        const unlight = () => {
          onLight(null);
        };
        return (
          <span key={key} className="n" tabIndex={0} onMouseEnter={light} onFocus={light} onMouseLeave={unlight} onBlur={unlight}>
            {segment.text}
          </span>
        );
      })}
    </p>
  );
}

function HowChecked() {
  return (
    <details>
      <summary>How this was checked</summary>
      <ul className="checks">
        <li>
          <PassIcon />
          <span>Each quote appears word for word on its cited page, after normalising spacing, dashes and symbols.</span>
        </li>
        <li>
          <PassIcon />
          <span>Each quote is at least four words long.</span>
        </li>
        <li>
          <PassIcon />
          <span>Every number in the answer appears in at least one quote.</span>
        </li>
      </ul>
    </details>
  );
}

function Drafts({ drafts, summary, open }: { drafts: readonly Draft[]; summary: string; open: boolean }) {
  return (
    <details open={open}>
      <summary>{summary}</summary>
      {drafts.map((draft, position) => (
        <div className="rejected" key={String(position)}>
          <span className="tag">Rejected, not verified</span>
          {draft.rejection !== null && (
            <p className="reason">
              <FailIcon />
              <span>
                {REJECTION_SENTENCES.get(draft.rejection.reason)}{" "}
                <span className="mono detail">{draft.rejection.detail}</span>
              </span>
            </p>
          )}
          <p>{draft.segments.map((segment) => segment.text).join("")}</p>
          {draft.citations.map((citation, index) => (
            <p className="quote" key={String(index)}>
              {location(citation)}: {citation.quote}
            </p>
          ))}
        </div>
      ))}
    </details>
  );
}

function location(citation: Citation): string {
  return `${citation.datasheet.toUpperCase()}, page ${String(citation.page)}`;
}
