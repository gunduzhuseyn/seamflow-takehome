import { PageHeader } from "@/components/page-header";
import { ClassifyPanel } from "@/features/classifications/components/classify-panel";
import { useQuestionLabel } from "@/features/classifications/question-label";

export function ClassifyRoute() {
  const [questionLabel, setQuestionLabel] = useQuestionLabel();
  return (
    <>
      <PageHeader
        title="Classify"
        description={`Current check: is this a ${questionLabel}?`}
      />
      <ClassifyPanel
        questionLabel={questionLabel}
        onQuestionLabelChange={setQuestionLabel}
      />
    </>
  );
}
