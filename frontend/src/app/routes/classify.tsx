import { PageHeader } from "@/components/page-header";
import { ClassifyPanel } from "@/features/classifications/components/classify-panel";

export function ClassifyRoute() {
  return (
    <>
      <PageHeader
        title="Classify"
        description="Drop images to get a verdict. Results update while the model works."
      />
      <ClassifyPanel />
    </>
  );
}
