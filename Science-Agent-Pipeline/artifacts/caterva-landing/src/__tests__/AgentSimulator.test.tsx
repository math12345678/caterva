import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AgentSimulator from "../cli/AgentSimulator";

describe("AgentSimulator", () => {
  it("renders the simulator window", () => {
    render(<AgentSimulator />);
    expect(screen.getByText(/agent simulator/i)).toBeInTheDocument();
  });

  it("renders the query input", () => {
    render(<AgentSimulator />);
    const input = screen.getByPlaceholderText(/simulate/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "text");
  });

  it("renders resolve and run buttons", () => {
    render(<AgentSimulator />);
    expect(
      screen.getByRole("button", { name: /resolve/i }),
    ).toBeInTheDocument();
  });
});
