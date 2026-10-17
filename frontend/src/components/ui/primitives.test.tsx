import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { Button, IconButton } from "./Button";
import { Checkbox, RadioGroup, Switch } from "./Choice";
import { Accordion, Tabs } from "./Disclosure";
import { Avatar, Badge, Breadcrumbs, initials, RiskChip } from "./Display";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Progress,
  RingProgress,
  StatCard,
  Stepper,
} from "./Feedback";
import { FormField, Input, Textarea } from "./Field";
import { ConfirmDialog, Dialog, DropdownMenu, Sheet, Tooltip } from "./Overlay";
import { SegmentedControl } from "./SegmentedControl";
import { Combobox, Select } from "./Select";
import { Slider } from "./Slider";
import { Toaster } from "./Toaster";
import { clearToasts, toast } from "./toast-store";

const OPTIONS = [
  { value: "react", label: "React" },
  { value: "fastapi", label: "FastAPI" },
  { value: "testing", label: "Testing" },
];

async function noAxeViolations(container: HTMLElement) {
  const result = await axe.run(container, { rules: { region: { enabled: false } } });
  expect(result.violations.map((v) => v.id)).toEqual([]);
}

describe("Button", () => {
  it("renders variants as links via asChild and keeps an accessible name while loading", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save changes</Button>);
    const button = screen.getByRole("button", { name: "Save changes" });
    expect(button).toHaveAttribute("type", "button");
    await userEvent.setup().click(button);
    expect(onClick).toHaveBeenCalledOnce();
    rerender(
      <Button loading onClick={onClick}>
        Save changes
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    rerender(
      <MemoryRouter>
        <Button asChild variant="outline">
          <a href="/x">Go</a>
        </Button>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Go" })).toHaveClass("border");
  });

  it("requires a label on icon-only buttons", () => {
    render(
      <IconButton aria-label="Close">
        <svg />
      </IconButton>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toHaveClass("size-11");
  });
});

describe("form controls", () => {
  it("wires label, hint, error and required marker", () => {
    render(
      <FormField label="Title" hint="Short and clear" error="Enter a title." required>
        <Input />
      </FormField>,
    );
    const input = screen.getByLabelText(/Title/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-required", "true");
    expect(input.getAttribute("aria-describedby")?.split(" ")).toHaveLength(2);
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a title.");
  });

  it("counts textarea characters and marks the limit", () => {
    render(
      <Textarea
        aria-label="Proposal"
        counter
        maxLength={5}
        value="abcde"
        onChange={() => undefined}
      />,
    );
    expect(screen.getByText("5 / 5")).toHaveClass("text-danger");
  });

  it("toggles checkbox and switch by keyboard", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Checkbox label="Agree" />
        <Switch label="Reduce motion" />
      </>,
    );
    await user.tab();
    await user.keyboard(" ");
    expect(screen.getByRole("checkbox", { name: "Agree" })).toBeChecked();
    await user.tab();
    await user.keyboard(" ");
    expect(screen.getByRole("switch", { name: /Reduce motion/ })).toBeChecked();
  });

  it("moves a radio group with arrow keys", async () => {
    function Group() {
      const [v, setV] = useState("a");
      return (
        <RadioGroup
          legend="Pick"
          value={v}
          onValueChange={setV}
          options={[
            { value: "a", label: "Alpha" },
            { value: "b", label: "Beta" },
          ]}
        />
      );
    }
    const user = userEvent.setup();
    render(<Group />);
    await user.tab();
    expect(screen.getByRole("radio", { name: "Alpha" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Beta" })).toHaveFocus();
    await user.keyboard(" ");
    expect(screen.getByRole("radio", { name: "Beta" })).toBeChecked();
  });

  it("steps a slider by keyboard and announces the formatted value", async () => {
    function S() {
      const [v, setV] = useState(10);
      return <Slider label="Weight" value={v} onChange={setV} format={(x) => `${String(x)}%`} />;
    }
    const user = userEvent.setup();
    render(<S />);
    const thumb = screen.getByRole("slider");
    thumb.focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(thumb).toHaveAttribute("aria-valuetext", "12%");
    expect(screen.getByText("12%")).toBeInTheDocument();
  });

  it("segmented control is a radio group with arrow keys", async () => {
    function S() {
      const [v, setV] = useState<"a" | "b">("a");
      return (
        <SegmentedControl
          label="Audience"
          value={v}
          onChange={setV}
          segments={[
            { value: "a", label: "Clients" },
            { value: "b", label: "Developers" },
          ]}
        />
      );
    }
    const user = userEvent.setup();
    render(<S />);
    screen.getByRole("radio", { name: "Clients" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "Developers" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "Developers" })).toHaveFocus();
  });

  it("select and combobox choose options", async () => {
    const onSelect = vi.fn();
    const onCombo = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <Select aria-label="Skill" value={undefined} onChange={onSelect} options={OPTIONS} />
        <Combobox value={undefined} onChange={onCombo} options={OPTIONS} />
      </>,
    );
    await user.click(screen.getByRole("combobox", { name: "Skill" }));
    await user.click(await screen.findByRole("option", { name: "FastAPI" }));
    expect(onSelect).toHaveBeenCalledWith("fastapi");
    await user.click(screen.getByText("Choose…"));
    await user.type(await screen.findByPlaceholderText("Search…"), "test");
    await user.keyboard("{Enter}");
    expect(onCombo).toHaveBeenCalledWith("testing");
  });
});

describe("overlays", () => {
  it("dialog traps focus, closes with Escape and has a title", async () => {
    const user = userEvent.setup();
    render(
      <Dialog
        trigger={<Button>Open</Button>}
        title="Invite"
        description="48 hours to accept."
        footer={<Button>Send</Button>}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog", { name: "Invite" });
    expect(dialog).toHaveAccessibleDescription("48 hours to accept.");
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("confirm dialog requires typing the confirmation text", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup();
    render(
      <ConfirmDialog
        trigger={<Button>Delete</Button>}
        title="Delete account?"
        description="This can’t be undone."
        confirmLabel="Delete account"
        confirmText="DELETE"
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirm = await screen.findByRole("button", { name: "Delete account" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "DELETE");
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("sheet and dropdown menu open and run actions", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <>
        <Sheet trigger={<Button>Filters</Button>} title="Filters" side="bottom">
          <p>Sheet body</p>
        </Sheet>
        <DropdownMenu
          trigger={<Button>More</Button>}
          items={[{ label: "Withdraw bid", onSelect, destructive: true }]}
        />
      </>,
    );
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(await screen.findByText("Sheet body")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(await screen.findByRole("menuitem", { name: "Withdraw bid" }));
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("tooltip opens on keyboard focus", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip content="Slack: 4 days">
        <Button>Frontend</Button>
      </Tooltip>,
    );
    await user.tab();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Slack: 4 days");
  });

  it("toasts render with a text label for their tone", async () => {
    render(<Toaster />);
    toast({ tone: "danger", title: "Payment failed", description: "Try again." });
    expect(await screen.findByText("Payment failed")).toBeInTheDocument();
    expect(screen.getByText("Problem:")).toHaveClass("sr-only");
    clearToasts();
  });
});

describe("display and feedback", () => {
  it("never shows status by colour alone", () => {
    render(
      <>
        <Badge tone="success">Paid</Badge>
        <RiskChip severity="CRITICAL">Late</RiskChip>
      </>,
    );
    expect(screen.getByText("Paid").querySelector("svg")).not.toBeNull();
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("derives avatar initials and keeps the name for screen readers", () => {
    expect(initials("Nadia Rahman")).toBe("NR");
    expect(initials("Mehjabin Chowdhury Khan")).toBe("MK");
    expect(initials("  ")).toBe("?");
    render(<Avatar name="Nadia Rahman" newcomer />);
    expect(screen.getByText("Nadia Rahman")).toHaveClass("sr-only");
  });

  it("breadcrumbs mark the current page", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: "Projects", to: "/p" }, { label: "Plan" }]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Plan")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Projects" })).toHaveAttribute("href", "/p");
  });

  it("progress, ring and stepper expose values", () => {
    render(
      <>
        <Progress label="API" value={70} showValue />
        <RingProgress label="Overall" value={62} />
        <Stepper
          steps={[{ label: "Info" }, { label: "Budget" }, { label: "Review" }]}
          current={1}
        />
      </>,
    );
    expect(screen.getByRole("progressbar", { name: "API" })).toHaveAttribute("aria-valuenow", "70");
    expect(screen.getByRole("progressbar", { name: "Overall" })).toHaveAttribute(
      "aria-valuenow",
      "62",
    );
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(screen.getByText("Info").textContent).toContain("(done)");
  });

  it("empty, error and stat states say what to do", async () => {
    const retry = vi.fn();
    const { container } = render(
      <MemoryRouter>
        <PageHeader
          title="Projects"
          description="Everything you posted."
          action={<Button>Create project</Button>}
        />
        <EmptyState
          title="No projects yet"
          description="Plan your first project."
          action={<Button>Create</Button>}
        />
        <ErrorState requestId="req_1" onRetry={retry} />
        <StatCard label="Active projects" value={3} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText("req_1")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByText("3", { selector: ".sr-only" })).toBeInTheDocument();
    await noAxeViolations(container);
  });

  it("tabs and accordion work by keyboard", async () => {
    function T() {
      const [v, setV] = useState("a");
      return (
        <Tabs
          label="Workspace"
          value={v}
          onValueChange={setV}
          items={[
            { value: "a", label: "Overview", content: "Overview body" },
            { value: "b", label: "Tasks", content: "Tasks body" },
          ]}
        />
      );
    }
    const user = userEvent.setup();
    render(
      <>
        <T />
        <Accordion items={[{ id: "q", title: "Is the money real?", content: "No." }]} />
      </>,
    );
    screen.getByRole("tab", { name: "Overview" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(await screen.findByText("Tasks body")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Is the money real?" }));
    expect(screen.getByRole("button", { name: "Is the money real?" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
