import { fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { classificationStore, TEST_SESSION_TOKEN } from "@/testing/handlers";
import { renderWithProviders } from "@/testing/render";

import { ClassifyPanel } from "./classify-panel";

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
  });

  it("shows the empty state before any upload", async () => {
    renderWithProviders(<ClassifyPanel />);

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
      renderWithProviders(<ClassifyPanel />);
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

  it("rejects a wrong type and an oversized file inline", async () => {
    renderWithProviders(<ClassifyPanel />);
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
});
