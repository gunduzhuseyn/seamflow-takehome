import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useSearchParams } from "react-router";

import { QueryResult } from "@/components/query-result";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import {
  exportClassificationsCsv,
  labelsOptions,
  listClassificationsOptions,
  type ClassificationFilters,
  type ClassificationStatus,
} from "../api";
import {
  formatDate,
  percent,
  REVIEW_STATUS_LABEL,
  VERDICT_LABEL,
  verdictLabel,
} from "../format";
import { Thumbnail } from "./thumbnail";

const LIMIT = 50;
const EXPORT_FILENAME = "classifications.csv";

const STATUS_LABEL: Record<ClassificationStatus, string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

type FilterName = keyof ClassificationFilters;

/** Only a known value passes from the URL to the API. */
function pick<T extends string>(
  value: string | null,
  allowed: Record<T, string>,
): T | undefined {
  return value !== null && value in allowed ? (value as T) : undefined;
}

/** The filters and the offset the URL search params hold. */
function readSearch(params: URLSearchParams): {
  filters: ClassificationFilters;
  offset: number;
} {
  const offset = Number(params.get("offset"));
  return {
    filters: {
      status: pick(params.get("status"), STATUS_LABEL),
      verdict: pick(params.get("verdict"), VERDICT_LABEL),
      review_status: pick(params.get("review_status"), REVIEW_STATUS_LABEL),
      question_label: params.get("question_label") ?? undefined,
    },
    offset: Number.isInteger(offset) && offset > 0 ? offset : 0,
  };
}

/** Hands the browser a file to save, then frees the object URL. */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Every classification in the organization, with filters, pages, and CSV
 * export. The filters and the page live in the URL, so a reload keeps them.
 */
export function HistoryTable() {
  const statusId = useId();
  const verdictId = useId();
  const reviewId = useId();
  const questionId = useId();
  const [searchParams, setSearchParams] = useSearchParams();
  const { filters, offset } = readSearch(searchParams);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const query = useQuery(
    listClassificationsOptions({
      limit: LIMIT,
      ...(offset > 0 && { offset }),
      ...filters,
    }),
  );
  const labels = useQuery(labelsOptions());
  // The URL can name a question the list of labels has not loaded or lost.
  const questionOptions =
    filters.question_label !== undefined &&
    !(labels.data ?? []).includes(filters.question_label)
      ? [filters.question_label, ...(labels.data ?? [])]
      : (labels.data ?? []);

  const setFilter = (name: FilterName, value: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value === "") {
          next.delete(name);
        } else {
          next.set(name, value);
        }
        // A new filter starts on the first page.
        next.delete("offset");
        return next;
      },
      { replace: true },
    );
  };

  const setOffset = (value: number) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value > 0) {
        next.set("offset", String(value));
      } else {
        next.delete("offset");
      }
      return next;
    });
  };

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await exportClassificationsCsv(filters);
      downloadBlob(blob, filename ?? EXPORT_FILENAME);
    } catch (error: unknown) {
      setExportError(error instanceof Error ? error.message : "Export failed");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor={statusId}>Status</Label>
          <NativeSelect
            id={statusId}
            value={filters.status ?? ""}
            onChange={(event) => setFilter("status", event.target.value)}
          >
            <option value="">All</option>
            {Object.entries(STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1">
          <Label htmlFor={verdictId}>Verdict</Label>
          <NativeSelect
            id={verdictId}
            value={filters.verdict ?? ""}
            onChange={(event) => setFilter("verdict", event.target.value)}
          >
            <option value="">All</option>
            {Object.entries(VERDICT_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1">
          <Label htmlFor={reviewId}>Review status</Label>
          <NativeSelect
            id={reviewId}
            value={filters.review_status ?? ""}
            onChange={(event) => setFilter("review_status", event.target.value)}
          >
            <option value="">All</option>
            {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1">
          <Label htmlFor={questionId}>Question</Label>
          <NativeSelect
            id={questionId}
            value={filters.question_label ?? ""}
            onChange={(event) =>
              setFilter("question_label", event.target.value)
            }
          >
            <option value="">All</option>
            {questionOptions.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <Button
          variant="outline"
          className="ml-auto"
          disabled={exporting}
          onClick={() => {
            void handleExport();
          }}
        >
          Export CSV
        </Button>
      </div>
      {exportError !== null && (
        <p role="alert" className="text-xs text-destructive">
          Export failed: {exportError}
        </p>
      )}
      <QueryResult
        query={query}
        isEmpty={(data) => data.items.length === 0}
        emptyMessage="No classifications match these filters."
      >
        {(data) => (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <span className="sr-only">Thumbnail</span>
                  </TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead>Submitted by</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Verdict</TableHead>
                  <TableHead>Final verdict</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <Thumbnail
                        src={item.thumbnail_url}
                        filename={item.filename}
                      />
                    </TableCell>
                    <TableCell className="max-w-48 truncate font-medium">
                      {item.filename}
                    </TableCell>
                    <TableCell>{item.submitted_by_name}</TableCell>
                    <TableCell>{item.question_label}</TableCell>
                    <TableCell>
                      {verdictLabel(item.verdict, item.verdict_labels)}
                    </TableCell>
                    <TableCell>
                      {verdictLabel(item.final_verdict, item.verdict_labels)}
                    </TableCell>
                    <TableCell>{percent(item.confidence)}</TableCell>
                    <TableCell>
                      {STATUS_LABEL[item.status]}
                      {item.review_status === "pending" && ", pending review"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatDate(item.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <nav
              aria-label="Pages"
              className="flex items-center justify-between gap-3 text-sm"
            >
              <p className="text-muted-foreground">
                Showing {offset + 1} to {offset + data.items.length} of{" "}
                {data.total}
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                >
                  Prev
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + LIMIT >= data.total}
                  onClick={() => setOffset(offset + LIMIT)}
                >
                  Next
                </Button>
              </div>
            </nav>
          </>
        )}
      </QueryResult>
    </div>
  );
}
