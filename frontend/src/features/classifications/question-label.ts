import { useState } from "react";

/** The question every new classification asks. The API default is the same. */
export const DEFAULT_QUESTION_LABEL = "hot dog";
const STORAGE_KEY_PREFIX = "seefood.question-label.";

/** One key per signed-in user, so a shared browser keeps the questions apart. */
function storageKey(userId: string): string {
  return STORAGE_KEY_PREFIX + userId;
}

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

function read(userId: string | null): string {
  if (userId === null) {
    return DEFAULT_QUESTION_LABEL;
  }
  try {
    const stored = localStorage.getItem(storageKey(userId));
    if (stored !== null && isValidQuestionLabel(stored)) {
      return stored;
    }
  } catch {
    // Storage blocked. The default is fine.
  }
  return DEFAULT_QUESTION_LABEL;
}

/**
 * The current question of one user, kept in localStorage across reloads.
 * A different user, or no user, starts from the default. The caller passes
 * the Clerk user id so the hook stays free of Clerk.
 */
export function useQuestionLabel(
  userId: string | null,
): [string, (label: string) => void] {
  const [state, setState] = useState(() => ({ userId, label: read(userId) }));
  // The user changed under a mounted route: re-read before this render shows
  // the previous user's question.
  if (state.userId !== userId) {
    setState({ userId, label: read(userId) });
  }
  const label = state.userId === userId ? state.label : read(userId);
  const update = (next: string) => {
    setState({ userId, label: next });
    if (userId === null) {
      return;
    }
    try {
      localStorage.setItem(storageKey(userId), next);
    } catch {
      // Storage blocked. The value lives until the next reload.
    }
  };
  return [label, update];
}
