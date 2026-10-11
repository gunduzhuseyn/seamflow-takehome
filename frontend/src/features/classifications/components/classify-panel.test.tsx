import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  classificationStore,
  completedRow,
  TEST_SESSION_TOKEN,
} from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { useQuestionLabel } from "../question-label";
import { ClassifyPanel } from "./classify-panel";

/** The panel as the route mounts it: the hook owns the label. */
function Panel() {
  const [label, setLabel] = useQuestionLabel();
  return (
    <>
      <p>Current check: is this a {label}?</p>
      <ClassifyPanel questionLabel={label} onQuestionLabelChange={setLabel} />
    </>
  );
}

vi.mock("@clerk/react", () => ({
  getToken: vi.fn(() => Promise.resolve(TEST_SESSION_TOKEN)),
}));

// jsdom has no object URLs.
Object.assign(URL, {
  createObjectURL: vi.fn(() => "blob:test"),
  revokeObjectURL: vi.fn(),
});

function dropFiles(files: File[]) {
  fireEvent.drop(screen.getByTestId("drop-zone"), {
    dataTransfer: { files, types: ["Files"] },
  });
}

describe("ClassifyPanel", () => {
  beforeEach(() => {
    classificationStore.reset();
    localStorage.clear();
  });

  it("shows the empty state before any upload", async () => {
    renderWithProviders(<Panel />);

    expect(
      await screen.findByText(
        "No results yet. Drop an image to get the first verdict.",
      ),
    ).toBeInTheDocument();
  });

  it(
    "uploads two dropped files and shows queued, then completed cards",
    { timeout: 10_000 },
    async () => {
      renderWithProviders(<Panel />);
      await screen.findByText(/No results yet/);

      const hotDog = new File(["hd"], "hotdog.jpg", { type: "image/jpeg" });
      const burger = new File(["burger"], "burger.png", { type: "image/png" });
      dropFiles([hotDog, burger]);

      // Two cards appear in status queued, with the local preview.
      expect(await screen.findAllByText("Queued")).toHaveLength(2);
      const results = screen.getByRole("region", { name: "Results" });
      expect(within(results).getAllByRole("img")).toHaveLength(2);

      // Three requests per file, in order, with the right key and type.
      expect(classificationStore.uploads).toHaveLength(2);
      expect(classificationStore.puts).toHaveLength(2);
      expect(classificationStore.rows).toHaveLength(2);
      const putByKey = new Map(
        classificationStore.puts.map((put) => [put.key, put]),
      );
      for (const upload of classificationStore.uploads) {
        expect(putByKey.has(upload.key)).toBe(true);
      }
      expect(classificationStore.puts.map((p) => p.contentType).sort()).toEqual(
        ["image/jpeg", "image/png"],
      );
      expect(classificationStore.puts.map((p) => p.bytes).sort()).toEqual([
        2, 6,
      ]);
      expect(classificationStore.rows.map((r) => r.filename).sort()).toEqual([
        "burger.png",
        "hotdog.jpg",
      ]);
      expect(classificationStore.rows.map((r) => r.question_label)).toEqual([
        "hot dog",
        "hot dog",
      ]);
      expect(screen.getAllByText("Is this a hot dog?")).toHaveLength(2);

      // The mock flips rows on the second poll, 2 s after the first.
      const poll = { timeout: 6000 };
      expect(await screen.findByText("Hot Dog", {}, poll)).toBeInTheDocument();
      expect(
        await screen.findByText("Not Hot Dog", {}, poll),
      ).toBeInTheDocument();
      expect(screen.getAllByText("Completed")).toHaveLength(2);
      expect(screen.getByText("93%")).toBeInTheDocument();
      expect(screen.getByText("61%")).toBeInTheDocument();
      expect(screen.getByText("Pending review")).toBeInTheDocument();
      expect(screen.getAllByText("1234 ms, $0.0031")).toHaveLength(2);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it(
    "sends the typed question, keeps it across a remount, and refuses a bad one",
    { timeout: 10_000 },
    async () => {
      const first = renderWithProviders(<Panel />);
      await screen.findByText(/No results yet/);
      const input = screen.getByLabelText("Is this a");
      expect(input).toHaveValue("hot dog");
      expect(
        screen.getByText("Current check: is this a hot dog?"),
      ).toBeVisible();

      fireEvent.change(input, { target: { value: "  Corn Dog " } });
      expect(
        screen.getByText("Current check: is this a corn dog?"),
      ).toBeVisible();
      dropFiles([new File(["cd"], "corn.jpg", { type: "image/jpeg" })]);
      await waitFor(() => {
        expect(classificationStore.rows).toHaveLength(1);
      });
      expect(classificationStore.rows[0].question_label).toBe("corn dog");
      expect(await screen.findByText("Is this a corn dog?")).toBeVisible();
      expect(
        await screen.findByText("Not Corn Dog", {}, { timeout: 6000 }),
      ).toBeVisible();

      // A bad draft shows the hint, leaves the question as it was, and
      // blocks the drop zone.
      fireEvent.change(input, { target: { value: "<b>" } });
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(
        screen.getByText(
          "Use 2 to 60 letters, digits, spaces, apostrophes, or hyphens. " +
            "Not allowed: ignore, instruction, system, assistant, prompt.",
        ),
      ).toBeVisible();
      expect(
        screen.getByText("Current check: is this a corn dog?"),
      ).toBeVisible();
      expect(screen.getByTestId("drop-zone")).toHaveAttribute(
        "aria-disabled",
        "true",
      );
      dropFiles([new File(["x"], "blocked.jpg", { type: "image/jpeg" })]);
      expect(classificationStore.uploads).toHaveLength(1);

      // A banned word is invalid client side, so no request is sent.
      fireEvent.change(input, { target: { value: "system prompt" } });
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(
        screen.getByText("Current check: is this a corn dog?"),
      ).toBeVisible();

      first.unmount();
      renderWithProviders(<Panel />);
      expect(screen.getByLabelText("Is this a")).toHaveValue("corn dog");
      expect(
        screen.getByText("Current check: is this a corn dog?"),
      ).toBeVisible();
    },
  );

  it("rejects a wrong type and an oversized file inline", async () => {
    renderWithProviders(<Panel />);
    await screen.findByText(/No results yet/);

    const text = new File(["x"], "notes.txt", { type: "text/plain" });
    const big = new File([""], "big.jpg", { type: "image/jpeg" });
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    dropFiles([text, big]);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getAllByRole("listitem")).toHaveLength(2);
    expect(alert).toHaveTextContent(
      "notes.txt: not a JPEG, PNG, WebP, or GIF image.",
    );
    expect(alert).toHaveTextContent("big.jpg: larger than 10 MB.");
    expect(classificationStore.uploads).toHaveLength(0);
  });

  it("sends card feedback to the review endpoint and shows the final verdict", async () => {
    const row = completedRow();
    classificationStore.rows.push(
      row,
      completedRow({
        filename: "burger.png",
        verdict: "no_match",
        confidence: 0.61,
        review_status: "pending",
      }),
    );
    renderWithProviders(<Panel />);

    // Only the completed, non-pending card asks for feedback.
    expect(await screen.findByText("Was this correct?")).toBeInTheDocument();
    expect(screen.getAllByText("Was this correct?")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Yes" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "No" }));

    await waitFor(() => {
      expect(classificationStore.reviews).toEqual([
        { id: row.id, body: { final_verdict: "no_match" } },
      ]);
    });
    expect(
      await screen.findByText("Final verdict: Not Hot Dog"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Was this correct?")).not.toBeInTheDocument();
    expect(screen.queryByText("Hot Dog")).not.toBeInTheDocument();
    expect(screen.getAllByText("Not Hot Dog")).toHaveLength(2);
  });
});
