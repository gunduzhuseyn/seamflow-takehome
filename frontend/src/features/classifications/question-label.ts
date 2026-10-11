import { useState } from "react";

/** The question every new classification asks. The API default is the same. */
export const DEFAULT_QUESTION_LABEL = "hot dog";
const STORAGE_KEY = "seefood.question-label";

/** Mirrors the API check: 2 to 60 letters, digits, spaces, apostrophes, hyphens. */
export const QUESTION_LABEL_PATTERN = /^[a-z0-9][a-z0-9 '-]{1,59}$/;
/** Mirrors the API list. The question reaches the model, so these never pass. */
export const QUESTION_LABEL_BANNED_WORDS = [
  "ignore",
  "instruction",
  "system",
  "assistant",
  "prompt",
] as const;
export const QUESTION_LABEL_HINT =
  "Use 2 to 60 letters, digits, spaces, apostrophes, or hyphens. " +
  `Not allowed: ${QUESTION_LABEL_BANNED_WORDS.join(", ")}.`;

/** Trimmed and lower-cased, as the API stores it. */
export function normalizeQuestionLabel(raw: string): string {
  return raw.trim().toLowerCase();
}

/** True when the API accepts the normalized label. */
export function isValidQuestionLabel(label: string): boolean {
  return (
    QUESTION_LABEL_PATTERN.test(label) &&
    !QUESTION_LABEL_BANNED_WORDS.some((word) => label.includes(word))
  );
}

function read(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null && isValidQuestionLabel(stored)) {
      return stored;
    }
  } catch {
    // Storage blocked. The default is fine.
  }
  return DEFAULT_QUESTION_LABEL;
}

/** The current question, kept in localStorage across reloads. */
export function useQuestionLabel(): [string, (label: string) => void] {
  const [label, setLabel] = useState(read);
  const update = (next: string) => {
    setLabel(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Storage blocked. The value lives until the next reload.
    }
  };
  return [label, update];
}
