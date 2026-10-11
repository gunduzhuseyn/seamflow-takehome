import type { ReviewStatus, Verdict, VerdictLabels } from "./api";

export const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

const dateTime = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

/** The generic names of the verdict values, for filters. A row has its own. */
export const VERDICT_LABEL: VerdictLabels = {
  match: "Match",
  no_match: "No match",
};

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  not_required: "Not required",
  pending: "Pending",
  reviewed: "Reviewed",
};

export function verdictLabel(
  verdict: Verdict | null,
  labels: VerdictLabels,
): string {
  return verdict === null ? "—" : labels[verdict];
}

export function oppositeVerdict(verdict: Verdict): Verdict {
  return verdict === "match" ? "no_match" : "match";
}

/** 0.93 becomes "93%". */
export function percent(fraction: number | null): string {
  return fraction === null ? "—" : `${Math.round(fraction * 100)}%`;
}

export function formatDate(iso: string): string {
  return dateTime.format(new Date(iso));
}
