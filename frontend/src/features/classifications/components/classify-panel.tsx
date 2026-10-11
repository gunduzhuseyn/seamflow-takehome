import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";

import { QueryResult } from "@/components/query-result";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  createClassification,
  createUpload,
  listClassificationsOptions,
  putToUploadUrl,
  type ClassificationList,
  type ClassificationOut,
} from "../api";
import { ClassificationCard } from "./classification-card";
import {
  isValidQuestionLabel,
  normalizeQuestionLabel,
  QUESTION_LABEL_HINT,
} from "../question-label";
import { screenFiles } from "../screen-files";
import { DropZone } from "./drop-zone";

const LIST_QUERY = { limit: 50 } as const;
const POLL_MS = 2000;

function inFlight(item: ClassificationOut): boolean {
  return item.status === "queued" || item.status === "processing";
}

function byNewest(a: ClassificationOut, b: ClassificationOut): number {
  return b.created_at.localeCompare(a.created_at);
}

type ClassifyPanelProps = {
  /** The question every new upload asks. Always a valid label. */
  questionLabel: string;
  onQuestionLabelChange: (label: string) => void;
};

/** The question form, drop zone, upload flow, and the results grid. */
export function ClassifyPanel({
  questionLabel,
  onQuestionLabelChange,
}: ClassifyPanelProps) {
  const queryClient = useQueryClient();
  const questionId = useId();
  const questionHintId = useId();
  // What the input shows. The label updates only when this is valid.
  const [questionDraft, setQuestionDraft] = useState(questionLabel);
  const questionValid = isValidQuestionLabel(
    normalizeQuestionLabel(questionDraft),
  );
  const [errors, setErrors] = useState<string[]>([]);
  const [uploading, setUploading] = useState(0);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  // Every object URL ever created, revoked on unmount.
  const objectUrls = useRef<string[]>([]);

  useEffect(
    () => () => {
      objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  const query = useQuery({
    ...listClassificationsOptions(LIST_QUERY),
    refetchInterval: (q) =>
      q.state.data?.items.some(inFlight) ? POLL_MS : false,
  });

  const submit = async (file: File) => {
    const upload = await createUpload({
      filename: file.name,
      content_type: file.type,
      size_bytes: file.size,
    });
    await putToUploadUrl(upload.upload_url, file);
    const row = await createClassification({
      key: upload.key,
      filename: file.name,
      question_label: questionLabel,
    });
    const previewUrl = URL.createObjectURL(file);
    objectUrls.current.push(previewUrl);
    setPreviews((prev) => ({ ...prev, [row.id]: previewUrl }));
    queryClient.setQueryData<ClassificationList>(
      listClassificationsOptions(LIST_QUERY).queryKey,
      (old) =>
        old && !old.items.some((item) => item.id === row.id)
          ? { items: [row, ...old.items], total: old.total + 1 }
          : old,
    );
  };

  const handleFiles = (files: File[]) => {
    const { accepted, rejected } = screenFiles(files);
    setErrors(rejected.map(({ file, reason }) => `${file.name}: ${reason}.`));
    if (accepted.length === 0) {
      return;
    }
    setUploading((n) => n + accepted.length);
    void Promise.all(
      accepted.map((file) =>
        submit(file)
          .catch((error: unknown) => {
            const message =
              error instanceof Error ? error.message : "upload failed";
            setErrors((prev) => [...prev, `${file.name}: ${message}.`]);
          })
          .finally(() => setUploading((n) => n - 1)),
      ),
    ).then(() =>
      queryClient.invalidateQueries({ queryKey: ["classifications"] }),
    );
  };

  const isEmpty = (data: ClassificationList) => data.items.length === 0;

  return (
    <div className="space-y-6">
      <section aria-label="Upload" className="space-y-2">
        <form
          aria-label="Question"
          className="flex flex-wrap items-center gap-2 text-sm"
          onSubmit={(event) => event.preventDefault()}
        >
          <Label htmlFor={questionId}>Is this a</Label>
          <Input
            id={questionId}
            value={questionDraft}
            maxLength={60}
            aria-invalid={!questionValid}
            aria-describedby={questionHintId}
            className="w-48"
            onChange={(event) => {
              const draft = event.target.value;
              setQuestionDraft(draft);
              const next = normalizeQuestionLabel(draft);
              if (isValidQuestionLabel(next)) {
                onQuestionLabelChange(next);
              }
            }}
          />
          <span aria-hidden="true">?</span>
          <span
            id={questionHintId}
            className={
              questionValid ? "sr-only" : "basis-full text-xs text-destructive"
            }
          >
            {QUESTION_LABEL_HINT}
          </span>
        </form>
        {query.data && isEmpty(query.data) && (
          <p className="text-sm text-muted-foreground">
            No results yet. Drop an image to get the first verdict.
          </p>
        )}
        <DropZone onFiles={handleFiles} disabled={!questionValid} />
        {uploading > 0 && (
          <p role="status" className="text-xs text-muted-foreground">
            {`Uploading ${uploading} ${uploading === 1 ? "file" : "files"}…`}
          </p>
        )}
        {errors.length > 0 && (
          <ul role="alert" className="space-y-0.5 text-xs text-destructive">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Results">
        <QueryResult query={query} isEmpty={isEmpty} emptyMessage="">
          {(data) => (
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[...data.items].sort(byNewest).map((item) => (
                <li key={item.id}>
                  <ClassificationCard
                    item={item}
                    localPreviewUrl={previews[item.id]}
                  />
                </li>
              ))}
            </ul>
          )}
        </QueryResult>
      </section>
    </div>
  );
}
