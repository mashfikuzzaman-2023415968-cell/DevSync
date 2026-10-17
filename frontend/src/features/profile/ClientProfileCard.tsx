/** Client organisation profile (spec §13.5 #19, §7.2): shown to developers on the client’s
 * projects. Saves with one button (short form). */
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, Skeleton } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { toast } from "@/components/ui/toast-store";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { useClientProfile, useUpdateClientProfile } from "./api";
import { isHttpsUrl } from "./schemas";

const schema = z.object({
  organization: z.string().trim().max(120, "Use at most 120 characters."),
  description: z.string().trim().max(2000, "Use at most 2,000 characters."),
  website: z
    .string()
    .trim()
    .max(300, "Use at most 300 characters.")
    .refine(isHttpsUrl, { message: "Use a full https:// address." }),
});
type Values = z.infer<typeof schema>;

export function ClientProfileCard() {
  const profile = useClientProfile();
  const update = useUpdateClientProfile();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    values: {
      organization: profile.data?.organization ?? "",
      description: profile.data?.description ?? "",
      website: profile.data?.website ?? "",
    },
  });
  const description = useWatch({ control: form.control, name: "description" });
  const submit = form.handleSubmit(async (values) => {
    try {
      await update.mutateAsync(values);
      toast({ tone: "success", title: "Organisation saved" });
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["organization", "description", "website"]))
        toast({ tone: "danger", title: "Not saved", description: messageFor(e) });
    }
  });
  const errors = form.formState.errors;
  return (
    <Card>
      <CardHeader
        title="Your organisation"
        description="Developers see this on your projects before they bid."
      />
      {profile.isPending ? (
        <div className="space-y-3 p-5" aria-hidden="true">
          <Skeleton className="h-11" />
          <Skeleton className="h-24" />
        </div>
      ) : profile.isError ? (
        <ErrorState onRetry={() => void profile.refetch()} />
      ) : (
        <form noValidate onSubmit={(e) => void submit(e)} className="space-y-4 p-5">
          <Field
            label="Organisation"
            autoComplete="organization"
            placeholder="Rahim Traders"
            maxLength={120}
            error={errors.organization?.message}
            {...form.register("organization")}
          />
          <FormField
            label="What you do"
            hint="Your business and the kind of software you need."
            error={errors.description?.message}
          >
            <Textarea
              counter
              maxLength={2000}
              rows={4}
              value={description}
              {...form.register("description")}
            />
          </FormField>
          <Field
            label="Website"
            type="url"
            inputMode="url"
            autoComplete="url"
            placeholder="https://"
            hint="Optional."
            error={errors.website?.message}
            {...form.register("website")}
          />
          <Button type="submit" variant="outline" loading={form.formState.isSubmitting}>
            Save organisation
          </Button>
        </form>
      )}
    </Card>
  );
}
