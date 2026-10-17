/** FileDropzone, CountdownTimer and SortableList (spec §17 Phase 3 frontend tests). */
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CountdownTimer, formatClock, secondsLeft } from "./CountdownTimer";
import { checkFile, FileDropzone, type FileRule } from "./FileDropzone";
import { SortableList } from "./SortableList";

const RULE: FileRule = {
  types: ["image/png", "image/jpeg"],
  maxBytes: 1024,
  description: "PNG or JPEG up to 1 KB",
};

function file(name: string, type: string, size: number): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("checkFile", () => {
  it("accepts an allowed type within the limit, including the boundary", () => {
    expect(checkFile(file("a.png", "image/png", 1024), RULE)).toBeNull();
  });
  it("rejects empty files, other types and files over the limit", () => {
    expect(checkFile(file("a.png", "image/png", 0), RULE)).toMatch(/empty/);
    expect(checkFile(file("a.svg", "image/svg+xml", 10), RULE)).toMatch(/PNG or JPEG/);
    expect(checkFile(file("a.png", "image/png", 1025), RULE)).toMatch(/limit/);
  });
});

describe("FileDropzone", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });

  it("is a labelled file input that reports the chosen file", async () => {
    const onFile = vi.fn();
    render(<FileDropzone label="Add an image" rule={RULE} onFile={onFile} preview="landscape" />);
    const input = screen.getByLabelText(/Add an image/);
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", "image/png,image/jpeg");
    await userEvent.upload(input, file("shot.png", "image/png", 100));
    expect(onFile).toHaveBeenCalledOnce();
    expect(screen.getByText("shot.png")).toBeInTheDocument();
    expect(screen.getByText(/without its location data/)).toBeInTheDocument();
  });

  it("explains a wrong type without calling onFile, and marks the input invalid", () => {
    const onFile = vi.fn();
    render(<FileDropzone label="Add an image" rule={RULE} onFile={onFile} />);
    const input = screen.getByLabelText(/Add an image/);
    fireEvent.change(input, { target: { files: [file("x.gif", "image/gif", 10)] } });
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose PNG or JPEG up to 1 KB.");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("accepts a dropped file and shows upload progress", () => {
    const onFile = vi.fn();
    const { rerender } = render(<FileDropzone label="Drop here" rule={RULE} onFile={onFile} />);
    const zone = screen.getByText("Drop here").closest("label");
    expect(zone).not.toBeNull();
    fireEvent.dragOver(zone as HTMLElement, { dataTransfer: { files: [] } });
    expect(zone).toHaveAttribute("data-over");
    fireEvent.drop(zone as HTMLElement, {
      dataTransfer: { files: [file("a.jpg", "image/jpeg", 10)] },
    });
    expect(onFile).toHaveBeenCalledOnce();
    rerender(<FileDropzone label="Drop here" rule={RULE} onFile={onFile} progress={0.4} />);
    expect(screen.getByRole("progressbar", { name: "Uploading" })).toHaveAttribute(
      "aria-valuenow",
      "40",
    );
    expect(screen.getByLabelText(/Drop here/)).toBeDisabled();
  });

  it("shows a server error passed in", () => {
    render(<FileDropzone label="Add" rule={RULE} onFile={vi.fn()} error="The image is damaged." />);
    expect(screen.getByRole("alert")).toHaveTextContent("The image is damaged.");
  });
});

describe("CountdownTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-18T05:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats minutes and seconds and never goes below zero", () => {
    expect(formatClock(600)).toBe("10:00");
    expect(formatClock(59.2)).toBe("1:00");
    expect(formatClock(5)).toBe("0:05");
    expect(formatClock(-3)).toBe("0:00");
  });

  it("corrects for the server clock offset", () => {
    const deadline = new Date("2026-10-18T05:10:00Z");
    expect(secondsLeft(deadline, 0)).toBe(600);
    expect(secondsLeft(deadline, 30_000)).toBe(570); // server is 30 s ahead
  });

  it("turns amber under a minute, danger under 15 s, and expires once", () => {
    const onExpire = vi.fn();
    const deadline = new Date("2026-10-18T05:01:01Z");
    const { container } = render(<CountdownTimer deadline={deadline} onExpire={onExpire} />);
    const root = container.firstElementChild;
    expect(root).toHaveAttribute("data-level", "normal");
    expect(screen.getByRole("timer")).toHaveTextContent("1:01");
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(root).toHaveAttribute("data-level", "warning");
    expect(screen.getByText("Under a minute")).toBeInTheDocument();
    expect(screen.getByText("Less than a minute left.")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(45_000);
    });
    expect(root).toHaveAttribute("data-level", "danger");
    expect(screen.getByText("Hurry")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(screen.getByRole("timer")).toHaveTextContent("0:00");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onExpire).toHaveBeenCalledOnce();
  });
});

describe("SortableList", () => {
  const items = [
    { id: "a", title: "Alpha" },
    { id: "b", title: "Beta" },
  ];

  it("gives each row a keyboard drag handle with a name and instructions", () => {
    render(
      <SortableList
        items={items}
        label={(i) => i.title}
        onReorder={vi.fn()}
        renderItem={(i) => <span>{i.title}</span>}
      />,
    );
    const handles = screen.getAllByRole("button", { name: /^Reorder/ });
    expect(handles.map((h) => h.getAttribute("aria-label"))).toEqual([
      "Reorder Alpha",
      "Reorder Beta",
    ]);
    expect(handles[0]).toHaveAttribute("aria-describedby");
    expect(screen.getByText(/press Space or Enter, use the arrow keys/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("disables the handles when asked", () => {
    render(
      <SortableList
        items={items}
        label={(i) => i.title}
        onReorder={vi.fn()}
        renderItem={(i) => <span>{i.title}</span>}
        disabled
      />,
    );
    for (const h of screen.getAllByRole("button", { name: /^Reorder/ })) expect(h).toBeDisabled();
  });
});
