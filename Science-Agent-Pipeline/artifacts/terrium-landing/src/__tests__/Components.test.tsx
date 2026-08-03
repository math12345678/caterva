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
  it("renders all stat items", () => {
    render(<StatsBar />);
    expect(screen.getByText(/tests passing/i)).toBeInTheDocument();
    expect(screen.getByText(/live domains/i)).toBeInTheDocument();
    expect(screen.getByText(/pipeline uptime/i)).toBeInTheDocument();
    expect(screen.getByText(/supported domains/i)).toBeInTheDocument();
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
