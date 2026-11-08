import { useState } from "react";
import { pageImageUrl, type Box, type Citation } from "./api";
import type { View } from "./App";

export interface PageMarking {
  citation: Citation;
  pageCount: number;
  /** False for a page cited by a rejected draft: outlined, never highlighted. */
  isVerified: boolean;
}

interface PageViewerProps {
  view: View["kind"];
  shown: PageMarking | null;
  litNumber: string | null;
}

const EMPTY_MESSAGES: Record<View["kind"], [string, string]> = {
  idle: ["The cited page appears here,", "with the quoted passage highlighted so you can check it against the original."],
  loading: ["", "The cited page appears here."],
  answered: ["No page to show.", "No verified passage points to a page."],
  failed: ["No page to show.", "The request failed before any answer came back."],
};

export function PageViewer({ view, shown, litNumber }: PageViewerProps) {
  if (shown === null) {
    const [heading, detail] = EMPTY_MESSAGES[view];
    return (
      <div className="empty-page">
        {heading !== "" && <strong>{heading}</strong>}
        <span>{detail}</span>
      </div>
    );
  }
  const { citation, pageCount, isVerified } = shown;
  const url = pageImageUrl(citation.datasheet, citation.page);
  return (
    <>
      <div className="viewer-bar">
        <span className="where">
          {citation.datasheet.toUpperCase()} datasheet, page {citation.page} of {pageCount}
        </span>
        <a href={url} target="_blank" rel="noreferrer">
          Open the page image
        </a>
      </div>
      {!isVerified && (
        <p className="viewer-note">
          Cited by a rejected draft. The dashed outline marks what it quoted; it is not verified.
        </p>
      )}
      {/* Keyed by URL so a new page starts in its loading state. */}
      <PageImage key={url} url={url} shown={shown} litNumber={litNumber} />
    </>
  );
}

function PageImage({ url, shown, litNumber }: { url: string; shown: PageMarking; litNumber: string | null }) {
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const { citation, isVerified } = shown;
  const marks = citation.marks;
  const label = `${citation.datasheet.toUpperCase()} page ${String(citation.page)}, ${
    marks === null ? "quote not located" : isVerified ? "quoted passage highlighted" : "cited passage outlined"
  }`;
  if (state === "failed") {
    return (
      <div className="empty-page">
        <strong>Could not render this page.</strong>
        <span>The server could not draw the page image. Try asking again.</span>
      </div>
    );
  }
  return (
    <div className="sheet" data-state={state}>
      <img
        src={url}
        alt={label}
        onLoad={() => {
          setState("ready");
        }}
        onError={() => {
          setState("failed");
        }}
      />
      {marks?.quote.map((box, index) => (
        <span key={`q${String(index)}`} className={isVerified ? "mark" : "mark unverified"} style={place(box)} />
      ))}
      {isVerified &&
        marks?.numbers.flatMap((number, index) =>
          number.boxes.map((box, part) => (
            <span
              key={`n${String(index)}-${String(part)}`}
              className={number.value === litNumber ? "number lit" : "number"}
              style={place(box)}
            />
          )),
        )}
    </div>
  );
}

// Marks are drawn a little larger than the glyph boxes so they do not clip
// ascenders and descenders.
const MARK_PADDING = 0.002;

function place(box: Box) {
  return {
    left: `${String((box.left - MARK_PADDING) * 100)}%`,
    top: `${String((box.top - MARK_PADDING) * 100)}%`,
    width: `${String((box.right - box.left + 2 * MARK_PADDING) * 100)}%`,
    height: `${String((box.bottom - box.top + 2 * MARK_PADDING) * 100)}%`,
  };
}
