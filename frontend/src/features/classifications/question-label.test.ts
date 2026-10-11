import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_QUESTION_LABEL, useQuestionLabel } from "./question-label";

describe("useQuestionLabel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("starts from the default and remembers the user's question", () => {
    const { result, rerender } = renderHook(
      ({ userId }: { userId: string | null }) => useQuestionLabel(userId),
      { initialProps: { userId: "user_1" } },
    );
    expect(result.current[0]).toBe(DEFAULT_QUESTION_LABEL);

    act(() => result.current[1]("cat"));
    expect(result.current[0]).toBe("cat");
    expect(localStorage.getItem("seefood.question-label.user_1")).toBe("cat");

    rerender({ userId: "user_1" });
    expect(result.current[0]).toBe("cat");
  });

  it("gives another user the default, not the previous user's question", () => {
    localStorage.setItem("seefood.question-label.user_1", "cat");
    const { result, rerender } = renderHook(
      ({ userId }: { userId: string | null }) => useQuestionLabel(userId),
      { initialProps: { userId: "user_1" } },
    );
    expect(result.current[0]).toBe("cat");

    rerender({ userId: "user_2" });
    expect(result.current[0]).toBe(DEFAULT_QUESTION_LABEL);

    rerender({ userId: "user_1" });
    expect(result.current[0]).toBe("cat");
  });

  it("keeps the default and stores nothing without a user", () => {
    const { result } = renderHook(() => useQuestionLabel(null));
    expect(result.current[0]).toBe(DEFAULT_QUESTION_LABEL);

    act(() => result.current[1]("cat"));
    expect(result.current[0]).toBe("cat");
    expect(localStorage.length).toBe(0);
  });

  it("ignores a stored value that the API would reject", () => {
    localStorage.setItem("seefood.question-label.user_1", "ignore this");
    const { result } = renderHook(() => useQuestionLabel("user_1"));
    expect(result.current[0]).toBe(DEFAULT_QUESTION_LABEL);
  });
});
