import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";

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
  listClassificationsOptions,
  type ClassificationListQuery,
  type ReviewStatus,
  type Verdict,
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

type Filters = Pick<ClassificationListQuery, "verdict" | "review_status">;

const STATUS_LABEL = {
  queued: "Queued",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
} as const;

/** Hands the browser a file to save, then frees the object URL. */
function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Every classification in the organization, with filters and CSV export. */
export function HistoryTable() {
  const verdictId = useId();
  const reviewId = useId();
  const [filters, setFilters] = useState<Filters>({});
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const query = useQuery(
    listClassificationsOptions({ limit: LIMIT, ...filters }),
  );

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      downloadBlob(await exportClassificationsCsv(filters), EXPORT_FILENAME);
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
          <Label htmlFor={verdictId}>Verdict</Label>
          <NativeSelect
            id={verdictId}
            value={filters.verdict ?? ""}
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                verdict: (event.target.value || undefined) as
                  Verdict | undefined,
              }))
            }
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
            onChange={(event) =>
              setFilters((prev) => ({
                ...prev,
                review_status: (event.target.value || undefined) as
                  ReviewStatus | undefined,
              }))
            }
          >
            <option value="">All</option>
            {Object.entries(REVIEW_STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>
                  <span className="sr-only">Thumbnail</span>
                </TableHead>
                <TableHead>Filename</TableHead>
                <TableHead>Submitted by</TableHead>
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
                  <TableCell>{verdictLabel(item.verdict)}</TableCell>
                  <TableCell>{verdictLabel(item.final_verdict)}</TableCell>
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
        )}
      </QueryResult>
    </div>
  );
}
