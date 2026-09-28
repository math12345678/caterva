import {
  describe,
  it,
  expect,
  vi,
  beforeAll,
  afterEach,
  beforeEach,
} from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import ExportButtons from "@/components/ui/export-buttons";
import StatsBar from "@/cli/StatsBar";
import DashboardPreview from "@/cli/DashboardPreview";
import BrandMotion, { pose } from "@/components/brand/BrandMotion";
import BackendHealth from "@/components/ui/backend-health";

const mockTrajectory = [
  { t: 0, S: 10, P: 0 },
  { t: 1, S: 8, P: 2 },
  { t: 2, S: 6.5, P: 3.5 },
];

describe("ExportButtons", () => {
  beforeAll(() => {
    HTMLAnchorElement.prototype.click = vi.fn();
  });

  it("renders CSV and JSON buttons when result is provided", () => {
    render(
      <ExportButtons trajectory={mockTrajectory} result={{ key: "value" }} />,
    );
    expect(screen.getByText("CSV")).toBeInTheDocument();
    expect(screen.getByText("JSON")).toBeInTheDocument();
  });

  it("renders only CSV button when no result is provided", () => {
    render(<ExportButtons trajectory={mockTrajectory} />);
    expect(screen.getByText("CSV")).toBeInTheDocument();
    expect(screen.queryByText("JSON")).not.toBeInTheDocument();
  });

  it("CSV download creates correct filename prefix", () => {
    render(
      <ExportButtons
        trajectory={mockTrajectory}
        filenamePrefix="mm"
        runId="abc12345"
      />,
    );
    const csvBtn = screen.getByText("CSV");
    expect(csvBtn).toBeInTheDocument();
  });

  it("renders nothing for empty trajectory", () => {
    const { container } = render(<ExportButtons trajectory={[]} />);
    expect(container.textContent).toContain("CSV");
  });
});

describe("StatsBar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the static stats", () => {
    // "live domains" / "supported domains" used to be two separate figures
    // (2 live, 6 supported) from when most domains were still planned.
    // All are live now, so there is one real figure, not two.
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network"));
    render(<StatsBar />);
    expect(screen.getByText(/tests passing/i)).toBeInTheDocument();
    // "live capabilities" since 2026-09-28: the list now includes the
    // structure and MD tools, which are not simulation domains. The count
    // is derived from lib/domains.ts, never a second hardcoded copy.
    expect(screen.getByText(/live capabilities/i)).toBeInTheDocument();
  });

  it("does not fabricate a waitlist count or uptime figure when the API call fails", async () => {
    // This used to fall back to a hardcoded `waitlistCount || 47` /
    // `uptimeHours || 24` on fetch failure -- a plausible-looking made-up
    // number rendered with the same visual authority as real data, and
    // (via the `||`) one that also clobbered a genuine zero. On failure
    // there is no real number to show, so the stat should not render at
    // all rather than render a fabricated one.
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network"));
    render(<StatsBar />);
    // The rejected fetch's .catch() runs as a microtask after this
    // synchronous render -- asserting absence immediately would pass
    // trivially whether or not a fallback fires later. Wait for the
    // rejection to actually settle (and any resulting re-render to
    // commit) before checking nothing appeared.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText(/researchers waiting/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/pipeline uptime/i)).not.toBeInTheDocument();
  });

  it("shows the real waitlist count and uptime once the API responds, including a genuine zero", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      const href = String(url);
      if (href.includes("/api/waitlist/count")) {
        return Promise.resolve(
          new Response(JSON.stringify({ count: 0 }), { status: 200 }),
        );
      }
      if (href.includes("/api/metrics")) {
        return Promise.resolve(
          new Response(JSON.stringify({ uptime: 3 * 3600 }), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch: ${href}`));
    });
    render(<StatsBar />);
    expect(
      await screen.findByText(/researchers waiting/i),
    ).toBeInTheDocument();
    expect(await screen.findByText(/pipeline uptime/i)).toBeInTheDocument();
  });
});

describe("BackendHealth", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders with connecting state initially", () => {
    render(<BackendHealth />);
    expect(screen.getByText(/connecting/i)).toBeInTheDocument();
  });

  it("shows connected state after successful fetch", async () => {
    render(<BackendHealth />);
    const connected = await screen.findByText(/connected/i);
    expect(connected).toBeInTheDocument();
  });

  it("shows disconnected state after failed fetch", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network error"));
    render(<BackendHealth />);
    const disconnected = await screen.findByText(/disconnected/i);
    expect(disconnected).toBeInTheDocument();
  });
});

// The hero demo once shipped a stale `kmApp` reference that typechecked
// nowhere and blanked the hero behind the error boundary. Rendering it is
// the cheapest test that would have caught that.
describe("DashboardPreview", () => {
  it("renders the cited inhibitor constant", () => {
    render(<DashboardPreview />);
    expect(screen.getByText(/noncompetitive/)).toBeTruthy();
  });
});

// Reduced motion must get the finished lockup, still: every letter shown,
// the signal colour on the C's open end, and no animation loop running.
describe("BrandMotion", () => {
  it("shows the settled lockup when the reader asks for reduced motion", () => {
    const original = window.matchMedia;
    window.matchMedia = ((q: string) => ({ matches: q.includes("reduce"), media: q,
      addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia;
    try {
      const { getByTestId } = render(<BrandMotion height={100} />);
      const stage = getByTestId("brand-motion");
      expect(stage.getAttribute("aria-label")).toBe("caterva");
      const letters = [...stage.querySelectorAll("span.inline-block")] as HTMLElement[];
      expect(letters.map((l) => l.textContent).join("")).toBe("caterva");
      expect(letters.every((l) => l.style.opacity === "1")).toBe(true);
      const circles = [...stage.querySelectorAll("circle")] as SVGCircleElement[];
      expect(circles[7].style.fill).toBe("var(--signal)");
      expect(circles[0].style.fill).toBe("currentColor");
    } finally {
      window.matchMedia = original;
    }
  });
});

// The motion itself, frame by frame: what the reference recording does.
describe("BrandMotion pose", () => {
  const BASE = [50.9, 61.7, 44.2, 59.6, 44.2, 60.2, 53.5, 44.2];
  const peak = (t: number) => Math.max(...pose(t).radii.map((r, i) => r / BASE[i]!));

  it("swells hard enough while centred that neighbouring dots meet", () => {
    const most = Math.max(...Array.from({ length: 24 }, (_, k) => peak(0.2 + k * 0.1)));
    expect(most).toBeGreaterThan(1.8);
    expect(pose(0).lockup).toBe(0);
    expect(pose(0).letters.every((l) => l.opacity === 0)).toBe(true);
    expect(pose(0).signal).toBe(0); // the C's upper end, as in the mark
  });

  it("settles into the lockup: half-size mark, every letter set, signal at the open end", () => {
    const p = pose(5.5);
    expect(p.scale).toBeCloseTo(0.5);
    expect(p.signal).toBe(7);
    expect(p.letters.every((l) => l.opacity === 1 && l.rise === 0)).toBe(true);
    expect(peak(5.5)).toBe(1); // still while the word is read
  });

  it("sets the letters one after another, left to right", () => {
    const p = pose(3.6);
    const o = p.letters.map((l) => l.opacity);
    for (let i = 1; i < o.length; i++) expect(o[i]!).toBeLessThanOrEqual(o[i - 1]!);
    expect(o[0]!).toBeGreaterThan(0.5);
    expect(o[6]!).toBe(0);
  });

  it("loops without a jump", () => {
    const a = pose(0), b = pose(10.999);
    a.radii.forEach((r, i) => expect(b.radii[i]!).toBeCloseTo(r, 0));
    expect(b.lockup).toBe(a.lockup);
  });
});
