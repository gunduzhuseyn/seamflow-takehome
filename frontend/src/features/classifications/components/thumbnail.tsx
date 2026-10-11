type ThumbnailProps = {
  src: string | null;
  filename: string;
};

/** A small fixed-size thumbnail for table rows. Grey box while none exists. */
export function Thumbnail({ src, filename }: ThumbnailProps) {
  if (src === null) {
    return <div aria-hidden className="h-10 w-14 rounded-md bg-muted" />;
  }
  return (
    <img
      src={src}
      alt={`Thumbnail of ${filename}`}
      className="h-10 w-14 rounded-md object-cover"
    />
  );
}
