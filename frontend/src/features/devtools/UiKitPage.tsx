/**
 * Development-only UI kit (spec §17 Phase 2 #9): every component and state on one page, in the
 * current theme, for visual baselines. Not part of production builds.
 */
import { Bell, Mail, Plus, Settings, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Mark } from "@/components/brand/Logo";
import { NodeArt } from "@/components/brand/NodeArt";
import { Still } from "@/components/brand/Still";
import { Button, IconButton } from "@/components/ui/Button";
import { Checkbox, RadioGroup, Switch } from "@/components/ui/Choice";
import { Accordion, Tabs } from "@/components/ui/Disclosure";
import {
  Avatar,
  Badge,
  Breadcrumbs,
  Card,
  CardHeader,
  NewcomerBadge,
  RiskChip,
  Skeleton,
} from "@/components/ui/Display";
import {
  Alert,
  EmptyState,
  ErrorState,
  PageHeader,
  Progress,
  RingProgress,
  StatCard,
  Stepper,
} from "@/components/ui/Feedback";
import { Field, FormField, Input, Textarea } from "@/components/ui/Field";
import { OtpInput } from "@/components/ui/OtpInput";
import {
  ConfirmDialog,
  Dialog,
  DropdownMenu,
  Popover,
  Sheet,
  Tooltip,
} from "@/components/ui/Overlay";
import { PasswordMeter } from "@/components/ui/PasswordMeter";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Combobox, Select } from "@/components/ui/Select";
import { Slider } from "@/components/ui/Slider";
import { toast } from "@/components/ui/toast-store";
import { usePreferences, type ThemePref } from "@/design/preferences";
import { formatMoney } from "@/lib/format";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`kit-${title}`} className="space-y-4">
      <h2 id={`kit-${title}`} className="text-h4 font-semibold text-text">
        {title}
      </h2>
      <Card className="space-y-6 p-6">{children}</Card>
    </section>
  );
}

const SKILLS = ["React", "FastAPI", "PostgreSQL", "Testing", "UI/UX", "DevOps"].map((s) => ({
  value: s.toLowerCase(),
  label: s,
}));

export default function UiKitPage() {
  const { theme, setTheme } = usePreferences();
  const [otp, setOtp] = useState("12");
  const [slider, setSlider] = useState(35);
  const [segment, setSegment] = useState<"a" | "b" | "c">("a");
  const [tab, setTab] = useState("one");
  const [select, setSelect] = useState<string | undefined>(undefined);
  const [combo, setCombo] = useState<string | undefined>("react");
  const [radio, setRadio] = useState("client");
  return (
    <div className="min-h-dvh bg-bg">
      <main id="main" className="mx-auto max-w-content space-y-10 px-4 py-10 sm:px-6">
        <PageHeader
          title="UI kit"
          description="Every DevSync component and state (development only)."
          breadcrumbs={
            <Breadcrumbs
              items={[
                { label: "Home", to: "/" },
                { label: "Developer tools" },
                { label: "UI kit" },
              ]}
            />
          }
          action={
            <SegmentedControl<ThemePref>
              label="Theme"
              value={theme}
              onChange={setTheme}
              segments={[
                { value: "light", label: "Light" },
                { value: "dark", label: "Dark" },
                { value: "system", label: "System" },
              ]}
            />
          }
        />

        <Section title="Buttons">
          <div className="flex flex-wrap items-center gap-3">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="outline">Outline</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive" icon={<Trash2 aria-hidden="true" />}>
              Delete project
            </Button>
            <Button variant="link">Link</Button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg" icon={<Plus aria-hidden="true" />}>
              Large
            </Button>
            <Button loading>Saving</Button>
            <Button disabled>Disabled</Button>
            <IconButton aria-label="Notifications">
              <Bell aria-hidden="true" />
            </IconButton>
            <IconButton aria-label="Settings" size="sm">
              <Settings aria-hidden="true" />
            </IconButton>
          </div>
        </Section>

        <Section title="Form fields">
          <div className="grid gap-6 md:grid-cols-2">
            <Field
              label="Email"
              type="email"
              placeholder="you@example.com"
              hint="We never share it."
            />
            <Field
              label="Project title"
              required
              error="Enter a title of at least 5 characters."
              defaultValue="App"
            />
            <FormField label="Disabled">
              <Input disabled defaultValue="Read only" />
            </FormField>
            <FormField label="Proposal" hint="Explain how you’d approach the work.">
              <Textarea
                counter
                maxLength={500}
                defaultValue="I have built three ordering systems."
              />
            </FormField>
            <FormField label="Skill">
              <Select
                value={select}
                onChange={setSelect}
                options={SKILLS}
                placeholder="Choose a skill"
              />
            </FormField>
            <FormField label="Search skills">
              <Combobox value={combo} onChange={setCombo} options={SKILLS} />
            </FormField>
          </div>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <Checkbox label="I agree to the terms" defaultChecked />
              <Checkbox
                label="Send me project invitations"
                description="At most one email a day."
              />
              <Checkbox label="Disabled option" disabled />
            </div>
            <div className="space-y-2">
              <Switch label="Reduce motion" />
              <Switch label="Email notifications" defaultChecked />
            </div>
            <RadioGroup
              legend="Account type"
              value={radio}
              onValueChange={setRadio}
              options={[
                { value: "client", label: "Client", description: "Hire a team" },
                { value: "developer", label: "Developer", description: "Find work" },
              ]}
            />
            <RadioGroup
              legend="Role cards"
              cards
              defaultValue="client"
              options={[
                {
                  value: "client",
                  label: "I want to hire a team",
                  description: "Plan a project and pay by milestone.",
                },
                {
                  value: "developer",
                  label: "I want to find work",
                  description: "Bid on projects and join teams.",
                },
              ]}
            />
            <Slider
              label="Competency weight"
              value={slider}
              onChange={setSlider}
              format={(v) => `${String(v)}%`}
            />
            <div className="space-y-2">
              <SegmentedControl<"a" | "b" | "c">
                label="Preset"
                value={segment}
                onChange={setSegment}
                segments={[
                  { value: "a", label: "Balanced" },
                  { value: "b", label: "Budget" },
                  { value: "c", label: "Quality" },
                ]}
              />
            </div>
            <OtpInput label="Verification code" value={otp} onChange={setOtp} />
            <div className="space-y-4">
              <PasswordMeter password="correct" />
              <PasswordMeter password="correct horse battery staple" />
            </div>
          </div>
        </Section>

        <Section title="Status">
          <div className="flex flex-wrap gap-2">
            <Badge>Draft</Badge>
            <Badge tone="primary">Bidding</Badge>
            <Badge tone="success">Paid</Badge>
            <Badge tone="warning">In review</Badge>
            <Badge tone="danger">Frozen</Badge>
            <Badge tone="info">Funded</Badge>
            <NewcomerBadge />
            <RiskChip severity="CRITICAL">Pushes the deadline by 2 days</RiskChip>
            <RiskChip severity="MEDIUM" />
            <RiskChip severity="LOW" />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Avatar name="Nadia Rahman" newcomer />
            <Avatar name="Arif Hossain" size="lg" />
            <Avatar name="Rahim" size="sm" />
            <Mark />
          </div>
          <div className="space-y-3">
            <Alert tone="info">Bids are sealed until the team is formed.</Alert>
            <Alert tone="success" title="Milestone approved">
              {formatMoney(1_710_000)} was released to the team.
            </Alert>
            <Alert tone="warning">The bidding deadline is tomorrow.</Alert>
            <Alert tone="danger">Email or password is incorrect.</Alert>
          </div>
        </Section>

        <Section title="Progress">
          <Stepper
            steps={["Info", "Requirements", "Skills & team", "Milestones", "Budget", "Review"].map(
              (label) => ({ label }),
            )}
            current={3}
          />
          <div className="grid gap-6 md:grid-cols-3">
            <Progress label="Inventory API" value={70} showValue />
            <Progress label="Share total" value={100} showValue tone="success" />
            <RingProgress value={62} label="Project progress" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Active projects"
              value={3}
              delta={{ value: "1 this week", direction: "up", good: true }}
            />
            <StatCard label="Wallet" value={8_500_000} format={(v) => formatMoney(Math.round(v))} />
            <StatCard label="Open for bids" value={2} />
            <StatCard label="Awaiting approval" value={1} hint="auto-approves in 4 days" />
          </div>
        </Section>

        <Section title="Navigation and disclosure">
          <Tabs
            label="Project"
            value={tab}
            onValueChange={setTab}
            items={[
              {
                value: "one",
                label: "Overview",
                content: <p className="text-body text-text-muted">Overview content.</p>,
              },
              {
                value: "two",
                label: "Tasks",
                content: <p className="text-body text-text-muted">Tasks content.</p>,
              },
              {
                value: "three",
                label: "Timeline",
                content: <p className="text-body text-text-muted">Timeline content.</p>,
              },
            ]}
          />
          <Accordion
            items={[
              { id: "a", title: "Is the money real?", content: "No, payments are simulated." },
              {
                id: "b",
                title: "How are teams chosen?",
                content: "By a balance of skill, teamwork, speed and cost.",
              },
            ]}
          />
        </Section>

        <Section title="Overlays">
          <div className="flex flex-wrap gap-3">
            <Dialog
              trigger={<Button variant="outline">Open dialog</Button>}
              title="Invite to team"
              description="Nadia will have 48 hours to accept."
              footer={<Button>Send invitation</Button>}
            >
              <Field label="Message (optional)" />
            </Dialog>
            <ConfirmDialog
              trigger={<Button variant="destructive">Cancel project</Button>}
              title="Cancel this project?"
              description="Bids are released and the developers are told. This can’t be undone."
              confirmLabel="Cancel project"
              confirmText="Online ordering system"
              onConfirm={() => undefined}
            />
            <Sheet
              trigger={<Button variant="outline">Open sheet</Button>}
              title="Place a bid"
              footer={<Button full>Submit bid</Button>}
            >
              <Field label="Price (৳)" inputMode="numeric" />
            </Sheet>
            <Popover trigger={<Button variant="outline">Popover</Button>}>
              Slack is the time a milestone can slip without moving the deadline.
            </Popover>
            <Tooltip content="Critical path: any delay moves the deadline">
              <Button variant="ghost">Tooltip</Button>
            </Tooltip>
            <DropdownMenu
              trigger={<Button variant="outline">Menu</Button>}
              items={[
                { label: "Edit", onSelect: () => undefined },
                { label: "Message", icon: <Mail aria-hidden="true" />, onSelect: () => undefined },
                "separator",
                { label: "Withdraw bid", destructive: true, onSelect: () => undefined },
              ]}
            />
            <Button
              variant="secondary"
              onClick={() => {
                toast({
                  tone: "success",
                  title: "Bid placed",
                  description: "You can edit it until the deadline.",
                });
              }}
            >
              Show toast
            </Button>
          </div>
        </Section>

        <Section title="States">
          <div className="grid gap-6 md:grid-cols-3">
            <div className="space-y-3" role="status" aria-label="Loading example">
              <Skeleton className="h-6 w-1/2" />
              <Skeleton className="h-4" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-24" />
            </div>
            <EmptyState
              art={<NodeArt />}
              title="No projects yet"
              description="Plan your first project to see it here."
              action={<Button>Create project</Button>}
            />
            <ErrorState requestId="req_7f3a9c" onRetry={() => undefined} />
          </div>
          <CardHeader
            title="Card header"
            description="One-line description."
            action={
              <Button size="sm" variant="outline">
                Action
              </Button>
            }
          />
          <div className="flex flex-wrap items-end gap-6">
            <Still name="hero-poster" className="w-64" />
            <Still name="team" className="w-48" />
          </div>
        </Section>
      </main>
    </div>
  );
}
