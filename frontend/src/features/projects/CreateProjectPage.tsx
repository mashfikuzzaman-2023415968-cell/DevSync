/**
 * Create-project wizard (spec §13.5, §13.9). Six steps — Info, Requirements, Skills & team,
 * Milestones, Budget, Review — each persisted to a DRAFT project as the client moves forward,
 * so the work is never lost. The Milestones step runs the critical-path method live; the Review
 * step publishes the draft for bidding, asking the client to acknowledge the risk if the plan
 * runs past the deadline (DECISIONS D40).
 */
import { ArrowLeft, ArrowRight, CircleCheck, CreditCard, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useBlocker, useNavigate } from "react-router";
import type { CpmPreview, Project } from "@/api/types";
import { api, ApiError } from "@/api/client";
import { Button, IconButton } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Choice";
import { Card, CardHeader } from "@/components/ui/Display";
import { Alert, PageHeader, Stepper } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { Dialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { useMe } from "@/features/auth/api";
import { useSkills } from "@/features/profile/api";
import { formatDays, formatMoney } from "@/lib/format";
import { MilestonesStep } from "./MilestonesStep";
import {
  useCreateProject,
  usePublishProject,
  useReplaceDependencies,
  useReplaceMilestones,
  useReplaceSlots,
  useUpdateProject,
  useVerifyPaymentMethod,
} from "./api";
import { newKey, toPaisa, type MilestoneRow, type SlotRow } from "./schemas";

const STEPS = [
  { label: "Info" },
  { label: "Requirements" },
  { label: "Skills & team" },
  { label: "Milestones" },
  { label: "Budget" },
  { label: "Review" },
];

interface Draft {
  id: string;
  version: number;
}

export default function CreateProjectPage() {
  const navigate = useNavigate();
  const me = useMe();
  const paymentVerified = me.data?.payment_verified === true;
  const skills = useSkills();
  const create = useCreateProject();

  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Local form state (persisted to the draft on each "Continue").
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState("");
  const [deadlineDays, setDeadlineDays] = useState(30);
  const [startDate, setStartDate] = useState("");
  const [slots, setSlots] = useState<SlotRow[]>([{ skill_id: "", count: 1, label: "" }]);
  const [milestones, setMilestones] = useState<MilestoneRow[]>([
    {
      key: newKey(),
      name: "",
      duration_days: 3,
      share_bp: 10_000,
      skill_ids: [],
      predecessor_keys: [],
    },
  ]);
  const [budgetTaka, setBudgetTaka] = useState("");
  const [bonusTaka, setBonusTaka] = useState("0");
  const [biddingDeadline, setBiddingDeadline] = useState("");
  const [cpm, setCpm] = useState<CpmPreview | null>(null);
  const [ack, setAck] = useState(false);
  // Unsaved-changes prompt (spec §13.5 screen 21): edits made since the last saved step.
  const [dirty, setDirty] = useState(false);
  const [published, setPublished] = useState(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !published && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (!dirty || published) return undefined;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty, published]);

  // Any edit marks the wizard dirty until the step is saved.
  const edit =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setDirty(true);
    };

  const draftId = draft?.id ?? "preview";
  const update = useUpdateProject(draftId);
  const putSlots = useReplaceSlots(draftId);
  const putMilestones = useReplaceMilestones(draftId);
  const putDeps = useReplaceDependencies(draftId);

  const teamSize = slots.reduce((s, r) => s + (r.count || 0), 0);
  const totalShareBp = milestones.reduce((s, m) => s + (m.share_bp || 0), 0);
  const busy =
    create.isPending ||
    update.isPending ||
    putSlots.isPending ||
    putMilestones.isPending ||
    putDeps.isPending;

  function problem(e: unknown): string {
    return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
  }

  /** Ensure a DRAFT exists, then return its id + current version. */
  async function ensureDraft(): Promise<Draft> {
    if (draft) return draft;
    const project = await create.mutateAsync({
      title: title.trim(),
      summary: summary.trim(),
      description: "",
      requirements: "",
      budget_paisa: 0,
      bonus_pool_paisa: 0,
      deadline_days: deadlineDays,
      team_size: 2,
    });
    const next = { id: project.id, version: project.version };
    setDraft(next);
    return next;
  }

  /** Slot, milestone and dependency replaces bump the server's version too; re-read it so the
   * next PATCH (sent with If-Match) isn't rejected as stale. */
  async function refreshVersion(d: Draft): Promise<Draft> {
    const project = await api<Project>(`/projects/${d.id}`);
    const next = { id: project.id, version: project.version };
    setDraft(next);
    return next;
  }

  async function patch(body: Parameters<typeof update.mutateAsync>[0]["body"], d: Draft) {
    const project = await update.mutateAsync({ body, version: d.version, projectId: d.id });
    const next = { id: project.id, version: project.version };
    setDraft(next);
    return next;
  }

  /** Save the current step; returns false (and shows an error) if it could not be saved. */
  async function saveStep(current: number): Promise<boolean> {
    setError(null);
    try {
      const d = await ensureDraft();
      if (current === 0) {
        await patch({ title: title.trim(), summary: summary.trim() }, d);
      } else if (current === 1) {
        await patch(
          {
            description: description.trim(),
            requirements: requirements.trim(),
            deadline_days: deadlineDays,
            start_date: startDate || null,
          },
          d,
        );
      } else if (current === 2) {
        await putSlots.mutateAsync(
          slots.map((r) => ({ skill_id: r.skill_id, count: r.count, label: r.label.trim() })),
        );
        await refreshVersion(d);
      } else if (current === 3) {
        const saved = await putMilestones.mutateAsync(
          milestones.map((m) => ({
            ...(m.savedId ? { id: m.savedId } : {}),
            name: m.name.trim(),
            description: "",
            duration_days: m.duration_days,
            share_bp: m.share_bp,
            skill_ids: m.skill_ids,
          })),
        );
        const keyToId = new Map(milestones.map((m, i) => [m.key, saved[i]?.id]));
        setMilestones((rows) => rows.map((m, i) => ({ ...m, savedId: saved[i]?.id })));
        const deps = milestones.flatMap((m) =>
          m.predecessor_keys.flatMap((p) => {
            const predecessor_id = keyToId.get(p);
            const successor_id = keyToId.get(m.key);
            return predecessor_id && successor_id ? [{ predecessor_id, successor_id }] : [];
          }),
        );
        await putDeps.mutateAsync(deps);
        await refreshVersion(d);
      } else if (current === 4) {
        await patch(
          {
            budget_paisa: toPaisa(Number(budgetTaka)),
            bonus_pool_paisa: toPaisa(Number(bonusTaka || "0")),
            bidding_deadline: biddingDeadline ? new Date(biddingDeadline).toISOString() : null,
          },
          d,
        );
      }
      setDirty(false);
      return true;
    } catch (e) {
      setError(problem(e));
      return false;
    }
  }

  async function next() {
    if (await saveStep(step)) setStep((s) => Math.min(STEPS.length - 1, s + 1));
  }
  function back() {
    setError(null);
    setStep((s) => Math.max(0, s - 1));
  }

  // Step-local validity gates "Continue".
  const canContinue = (() => {
    if (step === 0) return title.trim().length >= 5;
    if (step === 2) return teamSize >= 2 && teamSize <= 10 && slots.every((r) => r.skill_id);
    if (step === 3)
      return (
        milestones.length > 0 &&
        milestones.every((m) => m.name.trim()) &&
        totalShareBp === 10_000 &&
        !cpm?.cycle?.length
      );
    if (step === 4) return Number(budgetTaka) >= 1;
    return true;
  })();

  const skillOptions = (skills.data ?? []).map((s) => ({ value: s.id, label: s.name }));
  const exceeds = cpm != null && cpm.duration > deadlineDays;

  return (
    <>
      <PageHeader
        title="Create a project"
        description="Describe the work, split it into milestones and see the critical path before anyone bids."
      />
      {/* The 6-step stepper is wider than a tablet in its desktop form; let it scroll
          horizontally inside its own box rather than push the page wide (spec §13.14). */}
      <div className="mb-6 overflow-x-auto">
        <Stepper steps={STEPS} current={step} />
      </div>

      {error ? (
        <Alert tone="danger" title="That step could not be saved" className="mb-6">
          {error}
        </Alert>
      ) : null}

      {step === 0 && (
        <Card className="max-w-2xl">
          <CardHeader title="What are you building?" />
          <div className="mt-4 flex flex-col gap-4">
            <Field
              label="Project title"
              required
              value={title}
              onChange={(e) => {
                edit(setTitle)(e.target.value);
              }}
              placeholder="e.g. Online ordering system"
              maxLength={120}
            />
            <FormField label="One-line summary" hint="Shown in the marketplace list.">
              {(a11y) => (
                <Textarea
                  {...a11y}
                  value={summary}
                  onChange={(e) => {
                    edit(setSummary)(e.target.value);
                  }}
                  maxLength={300}
                  rows={2}
                />
              )}
            </FormField>
          </div>
        </Card>
      )}

      {step === 1 && (
        <Card className="max-w-2xl">
          <CardHeader title="Requirements and deadline" />
          <div className="mt-4 flex flex-col gap-4">
            <FormField label="Requirements" hint="What done looks like, constraints, must-haves.">
              {(a11y) => (
                <Textarea
                  {...a11y}
                  value={requirements}
                  onChange={(e) => {
                    edit(setRequirements)(e.target.value);
                  }}
                  maxLength={5000}
                  rows={6}
                />
              )}
            </FormField>
            <FormField label="Background (optional)">
              {(a11y) => (
                <Textarea
                  {...a11y}
                  value={description}
                  onChange={(e) => {
                    edit(setDescription)(e.target.value);
                  }}
                  maxLength={10000}
                  rows={3}
                />
              )}
            </FormField>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Deadline (days)"
                type="number"
                inputMode="numeric"
                min={1}
                max={365}
                required
                value={deadlineDays}
                onChange={(e) => {
                  edit(setDeadlineDays)(Number(e.target.value));
                }}
              />
              <Field
                label="Preferred start (optional)"
                type="date"
                value={startDate}
                onChange={(e) => {
                  edit(setStartDate)(e.target.value);
                }}
              />
            </div>
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card className="max-w-2xl">
          <CardHeader
            title="Skills and team"
            description="Add a slot per role. The team size is the total of the slot counts (2–10)."
          />
          <ul className="mt-4 flex flex-col gap-3">
            {slots.map((r, i) => (
              <li key={i} className="flex items-end gap-3 rounded-lg border border-border p-3">
                <div className="flex-1">
                  <FormField label="Skill" id={`slot-skill-${String(i)}`}>
                    {(a11y) => (
                      <Select
                        {...a11y}
                        value={r.skill_id || undefined}
                        onChange={(v) => {
                          setDirty(true);
                          setSlots((xs) => xs.map((x, j) => (j === i ? { ...x, skill_id: v } : x)));
                        }}
                        options={skillOptions}
                        placeholder="Choose a skill"
                      />
                    )}
                  </FormField>
                </div>
                <div className="w-24">
                  <Field
                    label="How many"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={10}
                    value={r.count}
                    onChange={(e) => {
                      setDirty(true);
                      setSlots((xs) =>
                        xs.map((x, j) => (j === i ? { ...x, count: Number(e.target.value) } : x)),
                      );
                    }}
                  />
                </div>
                <IconButton
                  aria-label="Remove slot"
                  disabled={slots.length <= 1}
                  onClick={() => {
                    setDirty(true);
                    setSlots((xs) => xs.filter((_, j) => j !== i));
                  }}
                >
                  <Trash2 aria-hidden="true" />
                </IconButton>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-between">
            <Button
              variant="outline"
              disabled={slots.length >= 20}
              onClick={() => {
                setDirty(true);
                setSlots((xs) => [...xs, { skill_id: "", count: 1, label: "" }]);
              }}
            >
              <Plus aria-hidden="true" />
              Add slot
            </Button>
            <p className="text-body-sm tabular text-text-muted">
              Team size: <span className="font-semibold text-text">{teamSize}</span>
            </p>
          </div>
          {(teamSize < 2 || teamSize > 10) && (
            <p className="mt-2 text-body-sm text-danger">A team needs between 2 and 10 people.</p>
          )}
        </Card>
      )}

      {step === 3 && (
        <MilestonesStep
          projectId={draftId}
          milestones={milestones}
          onChange={edit(setMilestones)}
          skills={skills.data ?? []}
          teamSize={teamSize}
          slotCount={slots.length}
          deadlineDays={deadlineDays}
          onResult={setCpm}
        />
      )}

      {step === 4 && (
        <Card className="max-w-2xl">
          <CardHeader
            title="Budget"
            description="The budget is held in escrow and released by milestone."
          />
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Budget (৳)"
              type="number"
              inputMode="numeric"
              min={1}
              required
              value={budgetTaka}
              onChange={(e) => {
                edit(setBudgetTaka)(e.target.value);
              }}
              placeholder="e.g. 120000"
            />
            <Field
              label="Bonus pool (৳, optional)"
              type="number"
              inputMode="numeric"
              min={0}
              value={bonusTaka}
              onChange={(e) => {
                edit(setBonusTaka)(e.target.value);
              }}
            />
            <Field
              label="Bidding closes (optional)"
              type="datetime-local"
              value={biddingDeadline}
              onChange={(e) => {
                edit(setBiddingDeadline)(e.target.value);
              }}
            />
          </div>
        </Card>
      )}

      {step === 5 && (
        <Card className="max-w-2xl">
          <CardHeader
            title="Review and publish"
            description="Publishing opens the project for bids. You can still cancel later."
          />
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-body-sm">
            <Summary label="Title" value={title || "—"} />
            <Summary label="Team size" value={String(teamSize)} />
            <Summary label="Milestones" value={String(milestones.length)} />
            <Summary label="Deadline" value={formatDays(deadlineDays)} />
            <Summary label="Planned duration" value={cpm ? formatDays(cpm.duration) : "—"} />
            <Summary
              label="Budget"
              value={budgetTaka ? formatMoney(toPaisa(Number(budgetTaka))) : "—"}
            />
          </dl>
          {exceeds && (
            <Alert tone="warning" title="The plan runs past your deadline" className="mt-5">
              The critical path is {formatDays(cpm.duration)}, longer than your{" "}
              {formatDays(deadlineDays)} deadline. You can still publish, but developers may not be
              able to meet it.
              <div className="mt-3">
                <Checkbox
                  checked={ack}
                  onCheckedChange={(v) => {
                    setAck(v === true);
                  }}
                  label="I understand the schedule risk and want to publish anyway"
                />
              </div>
            </Alert>
          )}
          <PaymentMethod verified={paymentVerified} />
        </Card>
      )}

      <div className="sticky bottom-0 mt-6 flex items-center justify-between gap-3 border-t border-border bg-bg/90 py-4 backdrop-blur">
        <Button variant="outline" onClick={back} disabled={step === 0 || busy}>
          <ArrowLeft aria-hidden="true" />
          Back
        </Button>
        {step < STEPS.length - 1 ? (
          <Button
            onClick={() => {
              void next();
            }}
            loading={busy}
            disabled={!canContinue}
          >
            Continue
            <ArrowRight aria-hidden="true" />
          </Button>
        ) : (
          <PublishButton
            projectId={draftId}
            disabled={!draft || !paymentVerified || (exceeds && !ack)}
            ack={ack}
            onDone={(id) => {
              setPublished(true);
              // Navigate after the "published" state is applied, so the prompt doesn't fire.
              window.setTimeout(() => {
                void navigate(`/client/projects/${id}/plan`);
              }, 0);
            }}
          />
        )}
      </div>

      <Dialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
        title="Leave without saving?"
        description="Changes on this step haven’t been saved. Earlier steps are already saved in your draft."
        footer={
          <>
            <Button
              variant="outline"
              onClick={() => {
                if (blocker.state === "blocked") blocker.reset();
              }}
            >
              Stay on this step
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (blocker.state === "blocked") blocker.proceed();
              }}
            >
              Leave without saving
            </Button>
          </>
        }
      >
        <p className="text-body-sm text-text-muted">
          Use “Continue” to save this step, or leave and lose these edits.
        </p>
      </Dialog>
    </>
  );
}

/** Payments are simulated (spec §0.2 rule 17); publishing still needs a verified method (D39). */
function PaymentMethod({ verified }: { verified: boolean }) {
  const verify = useVerifyPaymentMethod();
  if (verified) {
    return (
      <p className="mt-5 flex items-center gap-2 text-body-sm text-success">
        <CircleCheck className="size-4" aria-hidden="true" />
        Payment method verified
      </p>
    );
  }
  return (
    <Alert tone="info" title="Verify a payment method to publish" className="mt-5">
      The budget is held in escrow while the team works. Payments in DevSync are simulated, so
      verifying takes one click and no card details.
      <div className="mt-3">
        <Button
          variant="outline"
          size="sm"
          loading={verify.isPending}
          icon={<CreditCard aria-hidden="true" />}
          onClick={() => {
            verify.mutate(undefined, {
              onSuccess: () => {
                toast({ tone: "success", title: "Payment method verified" });
              },
              onError: (e) => {
                toast({
                  tone: "danger",
                  title: "Payment method not verified",
                  description: e instanceof ApiError ? e.message : "Please try again.",
                });
              },
            });
          }}
        >
          Verify payment method
        </Button>
      </div>
    </Alert>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-text-muted">{label}</dt>
      <dd className="font-medium text-text">{value}</dd>
    </div>
  );
}

function PublishButton({
  projectId,
  disabled,
  ack,
  onDone,
}: {
  projectId: string;
  disabled: boolean;
  ack: boolean;
  onDone: (id: string) => void;
}) {
  const publish = usePublishProject(projectId);
  return (
    <Button
      loading={publish.isPending}
      disabled={disabled}
      onClick={() => {
        publish.mutate(
          { acknowledge_schedule_risk: ack },
          {
            onSuccess: (project) => {
              toast({
                tone: "success",
                title: "Published",
                description: "Your project is open for bids.",
              });
              onDone(project.id);
            },
            onError: (e) => {
              toast({
                tone: "danger",
                title: "Could not publish",
                description: e instanceof ApiError ? e.message : "Please try again.",
              });
            },
          },
        );
      }}
    >
      Publish for bidding
    </Button>
  );
}
