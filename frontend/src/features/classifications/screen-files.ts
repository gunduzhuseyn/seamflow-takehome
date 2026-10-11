export const ACCEPTED_TYPES = [
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
];
export const MAX_BYTES = 10 * 1024 * 1024;

export type RejectedFile = { file: File; reason: string };

/** Splits files into accepted and rejected by type and size. */
export function screenFiles(files: File[]): {
  accepted: File[];
  rejected: RejectedFile[];
} {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];
  for (const file of files) {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      rejected.push({ file, reason: "not a JPEG, PNG, WebP, or GIF image" });
    } else if (file.size > MAX_BYTES) {
      rejected.push({ file, reason: "larger than 10 MB" });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}
