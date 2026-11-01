import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import recorded from "@/__fixtures__/api/workspace/runs.json";
import { useRunAddress } from "@/lib/runAddress";

function at(path: string) {
  const memory = memoryLocation({ path, record: true });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <Router hook={memory.hook} searchHook={memory.searchHook}>
      {children}
    </Router>
  );
  return { memory, wrapper };
}

describe("a run's address", () => {
  const id = recorded.runs[0].id;

  it("becomes the run's permalink once a run asked for here exists, replacing the entry", () => {
    const { memory, wrapper } = at("/prepare");
    const { rerender } = renderHook(({ run }) => useRunAddress("/prepare", run, null), {
      wrapper,
      initialProps: { run: null as { id: string } | null },
    });
    expect(memory.history).toEqual(["/prepare"]);
    rerender({ run: { id } });
    expect(memory.history).toEqual([`/prepare?run=${id}`]);
  });

  it("stays as it is for the run it was opened on", () => {
    const { memory, wrapper } = at(`/prepare?run=${id}`);
    renderHook(() => useRunAddress("/prepare", { id }, id), { wrapper });
    expect(memory.history).toEqual([`/prepare?run=${id}`]);
  });
});
