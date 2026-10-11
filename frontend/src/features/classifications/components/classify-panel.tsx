import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { QueryResult } from "@/components/query-result";

import {
  createClassification,
  createUpload,
  listClassificationsOptions,
  putToUploadUrl,
  type ClassificationList,
  type ClassificationOut,
} from "../api";
import { ClassificationCard } from "./classification-card";
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

/** Drop zone, upload flow, and the results grid. */
export function ClassifyPanel() {
  const queryClient = useQueryClient();
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
        {query.data && isEmpty(query.data) && (
          <p className="text-sm text-muted-foreground">
            No results yet. Drop an image to get the first verdict.
          </p>
        )}
        <DropZone onFiles={handleFiles} />
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
