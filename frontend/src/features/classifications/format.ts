import type { ReviewStatus, Verdict } from "./api";

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

export const VERDICT_LABEL: Record<Verdict, string> = {
  hot_dog: "Hot Dog",
  not_hot_dog: "Not Hot Dog",
};

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  not_required: "Not required",
  pending: "Pending",
  reviewed: "Reviewed",
};

export function verdictLabel(verdict: Verdict | null): string {
  return verdict === null ? "—" : VERDICT_LABEL[verdict];
}

export function oppositeVerdict(verdict: Verdict): Verdict {
  return verdict === "hot_dog" ? "not_hot_dog" : "hot_dog";
}

/** 0.93 becomes "93%". */
export function percent(fraction: number | null): string {
  return fraction === null ? "—" : `${Math.round(fraction * 100)}%`;
}

export function formatDate(iso: string): string {
  return dateTime.format(new Date(iso));
}
