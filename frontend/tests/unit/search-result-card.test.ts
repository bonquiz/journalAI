import { describe, expect, test, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import SearchResultCard from "../../src/lib/components/SearchResultCard.svelte";

afterEach(() => cleanup());

describe("SearchResultCard", () => {
  test("renders title, excerpt, score, reason", () => {
    const { getByText } = render(SearchResultCard, {
      props: {
        result: {
          entry_id: "e1",
          title: "Regenbogen-Traum",
          excerpt: "Ich war in einem Feld voller Regenbögen.",
          score: 94,
          reason: "Erwähnt einen Regenbogen-Traum",
        },
      },
    });
    expect(getByText("Regenbogen-Traum")).toBeTruthy();
    expect(getByText(/Regenbögen\./)).toBeTruthy();
    expect(getByText("94")).toBeTruthy();
    expect(getByText(/Erwähnt einen Regenbogen/)).toBeTruthy();
  });

  test("hides reason-line when null", () => {
    const { queryByTestId } = render(SearchResultCard, {
      props: { result: { entry_id: "e2", title: "t", excerpt: "e", score: 10, reason: null } },
    });
    expect(queryByTestId("reason-line")).toBeNull();
  });
});
