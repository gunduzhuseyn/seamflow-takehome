import { useId, useState, type ChangeEvent, type DragEvent } from "react";

import { cn } from "@/lib/utils";

import { ACCEPTED_TYPES } from "../screen-files";

type DropZoneProps = {
  onFiles: (files: File[]) => void;
};

/** Click or drop. The label is the drop target; the input is visually hidden. */
export function DropZone({ onFiles }: DropZoneProps) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    onFiles(Array.from(event.dataTransfer.files));
  };

  return (
    <label
      htmlFor={inputId}
      data-testid="drop-zone"
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 py-8 text-center text-sm transition-colors hover:bg-accent/40 focus-within:ring-3 focus-within:ring-ring/50",
        dragging && "border-ring bg-accent/60",
      )}
    >
      <span className="font-medium">Drop images here or click to choose</span>
      <span className="mt-1 text-xs text-muted-foreground">
        JPEG, PNG, WebP, or GIF. Up to 10 MB each. Several at once is fine.
      </span>
      <input
        id={inputId}
        type="file"
        multiple
        accept={ACCEPTED_TYPES.join(",")}
        onChange={handleChange}
        className="sr-only"
      />
    </label>
  );
}
