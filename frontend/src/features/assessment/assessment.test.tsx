/** Role assessment UI (role assessment spec §7, §11, §17.5). */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, type JsonBodyType } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssessmentResult, AssessmentStatus } from "@/api/types";
import { secondsLeft } from "@/components/ui/CountdownTimer";
import { server } from "@/test/server";
import { resumeAttempt } from "./api";
import { AssessmentRunner } from "./AssessmentRunner";
import { AssessmentStatusCard, canBid } from "./AssessmentStatusCard";
import { ResultView } from "./ResultView";
import { useBidDraft } from "./useBidDraft";
import { LeaveCounter } from "./useFocusGuard";

const API = "https://testserver/api/v1";
const PID = "p-1";
const SID = "s-1";
const AID = "a-1";

const BLUEPRINT = {
  label: "React · State and hooks, Components and props, Effects and data fetching",
  competencies: [
    { code: "state_hooks", name: "State and hooks", weight_bp: 4000, question_count: 5,
      reasons: ["Core skill of this role (React)", "The requirements mention: cart"] },
    { code: "components_props", name: "Components and props", weight_bp: 3000,
      question_count: 4, reasons: ["Core skill of this role (React)"] },
  ],
  question_count: 12,
  time_limit_seconds: 900,
  extra_time_seconds: 0,
  pass_overall: 60,
  floor: 40,
  heavy_weight: 20,
}; // prettier-ignore

function status(over: Partial<AssessmentStatus> = {}): AssessmentStatus {
  return {
    status: "REQUIRED",
    reason: null,
    message:
      "As a new developer on DevSync, you show your competency for this role with a short assessment.",
    rules_version: 1,
    blueprint: BLUEPRINT,
    attempt_id: null,
    open_elsewhere: null,
    result: null,
    next_allowed_at: null,
    fallback: null,
    bidding_deadline: null,
    bidding_closes_soon: false,
    ...over,
  };
}

const RESULT: AssessmentResult = {
  attempt_id: AID,
  label: BLUEPRINT.label,
  outcome: "PASSED",
  passed: true,
  score: 78,
  pass_overall: 60,
  competencies: [
    { code: "state_hooks", name: "State and hooks", weight_bp: 4000, score: 85 },
    { code: "components_props", name: "Components and props", weight_bp: 3000, score: 70 },
  ],
  strongest: "State and hooks",
  weakest: "Components and props",
  submitted_at: "2026-10-28T09:14:00Z",
  valid_until: "2027-04-26T09:14:00Z",
  next_allowed_at: null,
};

function question(i: number) {
  return {
    id: `q-${String(i)}`,
    index: i,
    total: 3,
    text: `Question number ${String(i + 1)}?`,
    code_snippet: i === 0 ? "const a = 1;\nconsole.log(a);" : null,
    options: ["Alpha", "Beta", "Gamma", "Delta"],
    competency: "State and hooks",
  };
}

function attemptState(over: Record<string, unknown> = {}) {
  const now = new Date();
  return {
    id: AID,
    label: BLUEPRINT.label,
    state: "OPEN",
    current_index: 0,
    total: 3,
    started_at: now.toISOString(),
    deadline_at: new Date(now.getTime() + 15 * 60_000).toISOString(),
    server_now: now.toISOString(),
    focus_leaves: 0,
    leave_limit: 2,
    question: question(0),
    result: null,
    attempt_token: "window-token-1",
    ...over,
  };
}

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

async function runner(over: Record<string, unknown> = {}) {
  server.use(
    http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
    http.post(`${API}/assessment-attempts/${AID}/resume`, () =>
      HttpResponse.json(attemptState(over) as JsonBodyType),
    ),
    http.post(`${API}/assessment-attempts/${AID}/heartbeat`, () =>
      HttpResponse.json({
        server_now: new Date().toISOString(),
        deadline_at: new Date().toISOString(),
      }),
    ),
  );
  const attempt = await resumeAttempt(AID);
  const onClose = vi.fn();
  wrap(<AssessmentRunner attempt={attempt} onClose={onClose} />);
  return onClose;
}

afterEach(() => {
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------- pure parts

describe("LeaveCounter", () => {
  it("counts a new leave with the next seq and merges signals within 5 s", () => {
    const counter = new LeaveCounter(0);
    expect(counter.signal(1000)).toBe(1);
    expect(counter.signal(3000)).toBeNull(); // full screen exit + tab switch together
    expect(counter.signal(5999)).toBeNull();
    expect(counter.signal(6000)).toBe(2);
  });

  it("continues after the leaves the server already counted (resume)", () => {
    const counter = new LeaveCounter(1);
    expect(counter.signal(0)).toBe(2);
  });
});

describe("canBid", () => {
  it("allows a bid only when no assessment is needed, it passed, or practice passes", () => {
    expect(canBid(status({ status: "NOT_REQUIRED" }))).toBe(true);
    expect(canBid(status({ status: "PASSED" }))).toBe(true);
    expect(canBid(status({ status: "REQUIRED" }))).toBe(false);
    expect(canBid(status({ status: "RETAKE_LOCKED" }))).toBe(false);
    const fallback = { skill_name: "Flutter", practice_score: 80, passes: true, pass_mark: 60 };
    expect(canBid(status({ status: "FALLBACK_PRACTICE", fallback }))).toBe(true);
    expect(
      canBid(status({ status: "FALLBACK_PRACTICE", fallback: { ...fallback, passes: false } })),
    ).toBe(false);
    expect(canBid(undefined)).toBe(false);
  });
});

describe("countdown", () => {
  it("counts down from the server's clock, not the browser's", () => {
    const deadline = new Date("2026-10-28T10:15:00Z");
    const browserNow = Date.parse("2026-10-28T12:00:00Z"); // two hours fast
    const offset = Date.parse("2026-10-28T10:00:00Z") - browserNow;
    expect(secondsLeft(deadline, offset, browserNow)).toBe(15 * 60);
  });
});

// ---------------------------------------------------------------------------- status card

describe("AssessmentStatusCard", () => {
  function show(s: AssessmentStatus) {
    server.use(
      http.get(`${API}/projects/${PID}/slots/${SID}/assessment`, () =>
        HttpResponse.json(s as JsonBodyType),
      ),
    );
    wrap(<AssessmentStatusCard projectId={PID} slotId={SID} onRun={vi.fn()} />);
  }

  it("explains a required assessment with its competencies, weights and reasons", async () => {
    const user = userEvent.setup();
    show(status());
    expect(await screen.findByText("Role assessment required")).toBeInTheDocument();
    expect(screen.getByText("State and hooks")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
    expect(screen.getByText(/12 questions, 15 minutes/)).toBeInTheDocument();
    expect(screen.queryByText(/requirements mention/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Why these?" }));
    expect(screen.getByText(/The requirements mention: cart/)).toBeInTheDocument();
  });

  it("asks for consent before starting and sends the rules version", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    server.use(
      http.get(`${API}/auth/csrf`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API}/projects/${PID}/slots/${SID}/assessment/attempts`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(attemptState() as JsonBodyType, { status: 201 });
      }),
    );
    show(status());
    await user.click(await screen.findByRole("button", { name: "Start assessment" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/can’t go back/)).toBeInTheDocument();
    expect(
      within(dialog).getByText(/never record your screen, camera or keystrokes/),
    ).toBeInTheDocument();
    const start = within(dialog).getByRole("button", { name: "Start assessment" });
    expect(start).toBeDisabled();
    await user.click(within(dialog).getByRole("checkbox", { name: "I understand and agree" }));
    await user.click(start);
    await waitFor(() => {
      expect(body).toEqual({ consent: true, rules_version: 1 });
    });
  });

  it.each([
    [{ status: "PASSED", result: RESULT }, /Role assessment passed: 78/],
    [
      {
        status: "RETAKE_LOCKED",
        result: { ...RESULT, outcome: "NOT_PASSED", passed: false, score: 52 },
        next_allowed_at: "2026-11-27T09:00:00Z",
      },
      /You can retake it on 27 Nov 2026/,
    ],
    [
      {
        status: "FALLBACK_PRACTICE",
        message:
          "A role assessment isn't available for this role yet, so your practice test result for Flutter is used.",
        fallback: { skill_name: "Flutter", practice_score: null, passes: false, pass_mark: 60 },
      },
      /Take the Flutter practice test/,
    ],
    [{ status: "CLOSED", message: "Bidding has closed for this project." }, /Bidding has closed/],
    [
      {
        status: "BLOCKED",
        reason: "SKILL_NOT_ON_PROFILE",
        message: "Add React to your profile to bid for this role.",
      },
      /Edit your profile/,
    ],
    [{ status: "IN_PROGRESS", attempt_id: AID }, /Resume assessment/],
    [
      { status: "OPEN_ELSEWHERE", open_elsewhere: "other" },
      /Finish or let your other assessment expire/,
    ],
  ] as const)("shows the %o state", async (over, text) => {
    show(status(over));
    expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
  });

  it("shows nothing when no assessment is needed", async () => {
    show(status({ status: "NOT_REQUIRED" }));
    await waitFor(() => {
      expect(screen.queryByText("Role assessment required")).not.toBeInTheDocument();
    });
    expect(screen.queryByTestId("assessment-card")).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------- runner

describe("AssessmentRunner", () => {
  it("shows one question with its code, answers with the keys and sends the window token", async () => {
    const user = userEvent.setup();
    const seen: { body: unknown; token: string | null }[] = [];
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/answer`, async ({ request }) => {
        seen.push({ body: await request.json(), token: request.headers.get("X-Attempt-Token") });
        return HttpResponse.json({
          status: "NEXT",
          current_index: 1,
          total: 3,
          question: question(1),
          result: null,
        });
      }),
    );
    expect(await screen.findByRole("heading", { name: "Question number 1?" })).toBeInTheDocument();
    expect(screen.getByText(/console.log\(a\)/)).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 3")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /back|previous/i })).not.toBeInTheDocument();
    await user.keyboard("2");
    expect(screen.getByRole("radio", { name: /Beta/ })).toBeChecked();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Question number 2?" })).toBeInTheDocument();
    expect(seen).toEqual([{ body: { question_id: "q-0", choice: 1 }, token: "window-token-1" }]);
    expect(screen.getByText("Question 2 of 3")).toBeInTheDocument();
  });

  it("asks before skipping and sends a skip as no choice", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/answer`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          status: "NEXT",
          current_index: 1,
          total: 3,
          question: question(1),
          result: null,
        });
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Skip" }));
    expect(await screen.findByText("Skip this question?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Skip question" }));
    await waitFor(() => {
      expect(body).toEqual({ question_id: "q-0", choice: null });
    });
  });

  it("shows the result when the last answer is scored, without any correct answers", async () => {
    const user = userEvent.setup();
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/answer`, () =>
        HttpResponse.json({
          status: "SCORED",
          current_index: 3,
          total: 3,
          question: null,
          result: RESULT,
        }),
      ),
    );
    await user.click(await screen.findByRole("radio", { name: /Alpha/ }));
    await user.click(screen.getByRole("button", { name: "Confirm answer" }));
    expect(await screen.findByRole("heading", { name: /Passed/ })).toBeInTheDocument();
    expect(screen.getAllByText("Components and props").length).toBeGreaterThan(0);
    expect(screen.queryByText(/correct answer/i)).not.toBeInTheDocument();
  });

  it("stops this window when the attempt continued in another one", async () => {
    const user = userEvent.setup();
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/answer`, () =>
        HttpResponse.json(
          {
            error: {
              code: "ATTEMPT_MOVED",
              message: "This assessment continued in another window.",
            },
          },
          { status: 409 },
        ),
      ),
    );
    await user.click(await screen.findByRole("radio", { name: /Alpha/ }));
    await user.click(screen.getByRole("button", { name: "Confirm answer" }));
    expect(
      await screen.findByRole("heading", { name: "This assessment continued in another window" }),
    ).toBeInTheDocument();
  });

  it("warns on the first leave and ends the attempt on the second", async () => {
    const seqs: number[] = [];
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/focus-events`, async ({ request }) => {
        const body = (await request.json()) as { seq: number };
        seqs.push(body.seq);
        return body.seq === 1
          ? HttpResponse.json({ status: "WARNING", focus_leaves: 1, leave_limit: 2, result: null })
          : HttpResponse.json({
              status: "TERMINATED", focus_leaves: 2, leave_limit: 2,
              result: { ...RESULT, outcome: "ENDED_EARLY", passed: false, valid_until: null,
                        next_allowed_at: "2026-11-27T09:00:00Z" },
            }); // prettier-ignore
      }),
    );
    await screen.findByRole("heading", { name: "Question number 1?" });
    const hide = (state: "hidden" | "visible") => {
      Object.defineProperty(document, "visibilityState", { configurable: true, value: state });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    const now = vi.spyOn(Date, "now");
    now.mockReturnValue(1_000_000);
    act(() => {
      hide("hidden");
    });
    hide("visible");
    expect(await screen.findByText("You left the assessment")).toBeInTheDocument();
    now.mockReturnValue(1_010_000); // 10 s later: a second, separate leave
    act(() => {
      hide("hidden");
    });
    hide("visible");
    expect(await screen.findByRole("heading", { name: /Ended early/ })).toBeInTheDocument();
    expect(seqs).toEqual([1, 2]);
    now.mockRestore();
  });

  it("ignores a short loss of focus (an OS notification)", async () => {
    let calls = 0;
    await runner();
    server.use(
      http.post(`${API}/assessment-attempts/${AID}/focus-events`, () => {
        calls += 1;
        return HttpResponse.json({
          status: "WARNING",
          focus_leaves: 1,
          leave_limit: 2,
          result: null,
        });
      }),
    );
    await screen.findByRole("heading", { name: "Question number 1?" });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const focused = vi.spyOn(document, "hasFocus");
    focused.mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("blur"));
      vi.advanceTimersByTime(1000);
      window.dispatchEvent(new Event("focus"));
      vi.advanceTimersByTime(5000);
    });
    expect(calls).toBe(0);
    act(() => {
      window.dispatchEvent(new Event("blur"));
      vi.advanceTimersByTime(3500);
    });
    await waitFor(() => {
      expect(calls).toBe(1);
    });
    focused.mockRestore();
  });
});

// -------------------------------------------------------------------------- result, draft

describe("ResultView", () => {
  it("shows the retake date and guidance when not passed", () => {
    render(
      <ResultView
        result={{ ...RESULT, outcome: "NOT_PASSED", passed: false, score: 52, valid_until: null,
                  next_allowed_at: "2026-11-27T09:00:00Z" }} // prettier-ignore
      />,
    );
    expect(screen.getByRole("heading", { name: /Not passed/ })).toBeInTheDocument();
    expect(screen.getByText(/retake this assessment on/)).toHaveTextContent(
      "retake this assessment on 27 Nov 2026",
    );
    expect(
      screen.getByText(/Practice tests can help with components and props/),
    ).toBeInTheDocument();
  });
});

describe("useBidDraft", () => {
  it("keeps the draft in sessionStorage and restores it after a reload", () => {
    const first = renderHook(() => useBidDraft(PID));
    act(() => {
      first.result.current.update({ slotId: SID, priceTaka: "16000", days: "20" });
    });
    first.unmount();
    const again = renderHook(() => useBidDraft(PID));
    expect(again.result.current.draft).toMatchObject({
      slotId: SID,
      priceTaka: "16000",
      days: "20",
    });
    act(() => {
      again.result.current.clear();
    });
    expect(window.sessionStorage.getItem(`devsync:bid-draft:${PID}`)).toBeNull();
  });
});
