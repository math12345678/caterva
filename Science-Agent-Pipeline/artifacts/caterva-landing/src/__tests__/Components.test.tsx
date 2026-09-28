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
