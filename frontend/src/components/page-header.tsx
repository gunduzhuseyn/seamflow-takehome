type PageHeaderProps = {
  title: string;
  /** One sentence. */
  description: string;
};

/** The header of every page: a title and one line of description. */
export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <header className="mb-6">
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="text-sm text-muted-foreground">{description}</p>
    </header>
  );
}
