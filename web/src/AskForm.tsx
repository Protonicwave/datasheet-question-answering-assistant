import type { KeyboardEvent, SyntheticEvent } from "react";
import { MAX_QUESTION_CHARACTERS } from "./api";

interface AskFormProps {
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmit: (question: string) => void;
  isBusy: boolean;
}

export function AskForm({ question, onQuestionChange, onSubmit, isBusy }: AskFormProps) {
  const trimmed = question.trim();
  const canAsk = trimmed !== "" && !isBusy;

  function submit(event: SyntheticEvent) {
    event.preventDefault();
    if (canAsk) onSubmit(trimmed);
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      submit(event);
    }
  }

  return (
    <form className="ask" onSubmit={submit}>
      <label htmlFor="question">Ask a datasheet</label>
      <div className="ask-box">
        <textarea
          id="question"
          rows={2}
          maxLength={MAX_QUESTION_CHARACTERS}
          placeholder="For example: what is the sleep current of the BME280?"
          value={question}
          onChange={(event) => {
            onQuestionChange(event.target.value);
          }}
          onKeyDown={submitOnEnter}
        />
        <button className="btn" type="submit" disabled={!canAsk}>
          {isBusy ? "Asking" : "Ask"}
        </button>
      </div>
      <p className="hint">
        Name the part to search only its datasheet. <kbd>Enter</kbd> to ask, <kbd>Shift</kbd>{" "}
        <kbd>Enter</kbd> for a new line.
      </p>
    </form>
  );
}
