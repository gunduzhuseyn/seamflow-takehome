import { useState } from "react";

/** The question every new classification asks. The API default is the same. */
export const DEFAULT_QUESTION_LABEL = "hot dog";
const STORAGE_KEY = "seefood.question-label";

/** Mirrors the API check: 2 to 60 letters, digits, spaces, apostrophes, hyphens. */
export const QUESTION_LABEL_PATTERN = /^[a-z0-9][a-z0-9 '-]{1,59}$/;
export const QUESTION_LABEL_HINT =
  "Use 2 to 60 letters, digits, spaces, apostrophes, or hyphens.";

/** Trimmed and lower-cased, as the API stores it. */
export function normalizeQuestionLabel(raw: string): string {
  return raw.trim().toLowerCase();
}

function read(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null && QUESTION_LABEL_PATTERN.test(stored)) {
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
