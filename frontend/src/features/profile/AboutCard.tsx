/** Profile basics with autosave (spec §13.5 #15): headline, bio, availability, GitHub, time
 * zone and who can see the profile. */
import { zodResolver } from "@hookform/resolvers/zod";
import { CircleAlert, CircleCheck, LoaderCircle } from "lucide-react";
import { useCallback, useMemo } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import type { DeveloperProfile, DeveloperProfileUpdate } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { RadioGroup } from "@/components/ui/Choice";
import { Card, CardHeader } from "@/components/ui/Display";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { Combobox } from "@/components/ui/Select";
import { applyFieldErrors } from "@/features/auth/errors";
import { aboutSchema, type AboutValues } from "./schemas";
import { useUpdateDeveloperProfile } from "./api";
import { useAutosave, type SaveState } from "./useAutosave";

const FALLBACK_ZONES = ["Asia/Dhaka", "Asia/Kolkata", "Asia/Dubai", "Europe/London", "UTC"];

function timeZones(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return FALLBACK_ZONES;
  }
}

export function SaveIndicator({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
  return (
    <span aria-live="polite" className="inline-flex min-h-9 items-center gap-1.5 text-body-sm">
      {state === "saving" ? (
        <>
          <LoaderCircle
            className="size-4 animate-spin text-text-muted motion-reduce:animate-none"
            aria-hidden="true"
          />
          <span className="text-text-muted">Saving…</span>
        </>
      ) : null}
      {state === "saved" ? (
        <>
          <CircleCheck className="size-4 text-success" aria-hidden="true" />
          <span className="text-text-muted">Saved</span>
        </>
      ) : null}
      {state === "error" ? (
        <>
          <CircleAlert className="size-4 text-danger" aria-hidden="true" />
          <span className="text-danger">Not saved.</span>
          <Button variant="link" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </>
      ) : null}
    </span>
  );
}

function toValues(p: DeveloperProfile): AboutValues {
  return {
    headline: p.headline,
    bio: p.bio,
    hours_per_week: p.hours_per_week,
    github_username: p.github_username ?? "",
    timezone: p.timezone,
    visibility: p.visibility,
  };
}

export function AboutCard({ profile }: { profile: DeveloperProfile }) {
  const update = useUpdateDeveloperProfile();
  const saved = useMemo(() => toValues(profile), [profile]);
  const form = useForm<AboutValues>({
    resolver: zodResolver(aboutSchema),
    defaultValues: saved,
    mode: "onChange",
  });
  const values = useWatch({ control: form.control }) as AboutValues;
  const zones = useMemo(
    () => timeZones().map((z) => ({ value: z, label: z.replace(/_/g, " ") })),
    [],
  );

  const save = useCallback(
    async (changes: Partial<AboutValues>) => {
      const body: DeveloperProfileUpdate = {};
      for (const [k, v] of Object.entries(changes)) {
        const key = k as keyof AboutValues;
        if (key === "hours_per_week") body.hours_per_week = Number(v);
        else if (key === "github_username") body.github_username = v === "" ? null : String(v);
        else if (key === "visibility") body.visibility = v as DeveloperProfile["visibility"];
        else body[key] = String(v);
      }
      try {
        await update.mutateAsync(body);
      } catch (e) {
        applyFieldErrors(e, form.setError, [
          "headline",
          "bio",
          "hours_per_week",
          "github_username",
          "timezone",
          "visibility",
        ]);
        throw e;
      }
    },
    [update, form.setError],
  );
  const { state, retry } = useAutosave(values, saved, save, form.formState.isValid);
  const errors = form.formState.errors;

  return (
    <Card>
      <CardHeader
        title="About you"
        description="Clients see this when they review your bid. Changes save as you type."
        action={
          <SaveIndicator
            state={state}
            onRetry={() => {
              void retry();
            }}
          />
        }
      />
      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
        }}
        className="grid gap-5 p-5 md:grid-cols-2"
      >
        <div className="md:col-span-2">
          <Field
            label="Headline"
            placeholder="Frontend developer who builds accessible forms"
            maxLength={120}
            hint="One line about what you do best."
            error={errors.headline?.message}
            {...form.register("headline")}
          />
        </div>
        <FormField
          label="About"
          className="md:col-span-2"
          hint="Your experience, the kind of work you enjoy and how you like to collaborate."
          error={errors.bio?.message}
        >
          <Textarea
            counter
            maxLength={2000}
            rows={5}
            value={values.bio}
            {...form.register("bio")}
          />
        </FormField>
        <Field
          label="Hours per week"
          type="number"
          inputMode="numeric"
          min={1}
          max={80}
          hint="How much time you can give a project (1–80)."
          error={errors.hours_per_week?.message}
          {...form.register("hours_per_week")}
        />
        <Field
          label="GitHub username"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="nadia-dev"
          hint="Used to link commits to tasks once you join a team."
          error={errors.github_username?.message}
          {...form.register("github_username")}
        />
        <FormField label="Time zone" error={errors.timezone?.message}>
          {(a11y) => (
            <Controller
              control={form.control}
              name="timezone"
              render={({ field }) => (
                <Combobox
                  {...a11y}
                  value={field.value}
                  onChange={field.onChange}
                  options={zones}
                  searchPlaceholder="Search time zones…"
                />
              )}
            />
          )}
        </FormField>
        <Controller
          control={form.control}
          name="visibility"
          render={({ field }) => (
            <RadioGroup
              className="md:col-span-2"
              legend="Who can see your profile"
              value={field.value}
              onValueChange={field.onChange}
              options={[
                {
                  value: "PUBLIC",
                  label: "Everyone",
                  description: "Anyone with the link, signed in or not. Never your email or phone.",
                },
                {
                  value: "CLIENTS_ONLY",
                  label: "Clients only",
                  description: "Only signed-in clients (and you) can open it.",
                },
              ]}
            />
          )}
        />
      </form>
    </Card>
  );
}
