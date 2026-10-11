import { useAuth } from "@clerk/react";

import { PageHeader } from "@/components/page-header";
import { ClassifyPanel } from "@/features/classifications/components/classify-panel";
import { useQuestionLabel } from "@/features/classifications/question-label";

export function ClassifyRoute() {
  const { userId } = useAuth();
  const [questionLabel, setQuestionLabel] = useQuestionLabel(userId ?? null);
  return (
    <>
      <PageHeader
        title="Classify"
        description={`Drop images to get a verdict on the current check: is this a ${questionLabel}?`}
      />
      <ClassifyPanel
        questionLabel={questionLabel}
        onQuestionLabelChange={setQuestionLabel}
      />
    </>
  );
}
