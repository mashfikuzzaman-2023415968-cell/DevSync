/** Certificates and reviews from other platforms (spec §7.2, §7.7): uploaded with evidence,
 * pending until an admin verifies them; only verified ones appear publicly or count later. */
import { zodResolver } from "@hookform/resolvers/zod";
import { FileText, Trash2 } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useQueryClient } from "@tanstack/react-query";
import { fileUrl } from "@/api/client";
import type { Certificate, ExternalReview } from "@/api/types";
import { Button, IconButton } from "@/components/ui/Button";
import { Badge, Card, CardHeader, Skeleton, type Tone } from "@/components/ui/Display";
import { ErrorState } from "@/components/ui/Feedback";
import { Field } from "@/components/ui/Field";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { toast } from "@/components/ui/toast-store";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import { formatDate, formatScore } from "@/lib/format";
import {
  keys,
  uploadCertificate,
  uploadExternalReview,
  useCertificates,
  useDeleteCertificate,
  useDeleteExternalReview,
  useExternalReviews,
} from "./api";
import {
  CERTIFICATE_RULE,
  certificateSchema,
  REVIEW_RULE,
  reviewSchema,
  type CertificateValues,
  type ReviewValues,
} from "./schemas";

const STATUS: Record<Certificate["status"], { tone: Tone; label: string }> = {
  PENDING: { tone: "warning", label: "Pending admin verification" },
  VERIFIED: { tone: "success", label: "Verified" },
  REJECTED: { tone: "danger", label: "Not verified" },
};

function StatusBadge({ status, reason }: { status: Certificate["status"]; reason: string | null }) {
  const s = STATUS[status];
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Badge tone={s.tone}>{s.label}</Badge>
      {status === "REJECTED" && reason ? (
        <span className="text-caption text-text-muted">{reason}</span>
      ) : null}
    </span>
  );
}

function useUploadState() {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [fileError, setFileError] = useState<string>();
  const [reset, setReset] = useState(0);
  return {
    file,
    setFile,
    progress,
    setProgress,
    fileError,
    setFileError,
    reset,
    done: () => {
      setFile(null);
      setReset((n) => n + 1);
    },
  };
}

function EvidenceRow({
  title,
  detail,
  fileId,
  fileName,
  status,
  reason,
  onDelete,
}: {
  title: string;
  detail: string;
  fileId: string;
  fileName: string;
  status: Certificate["status"];
  reason: string | null;
  onDelete: () => Promise<void>;
}) {
  return (
    <li className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-body font-medium text-text">{title}</p>
        <p className="text-body-sm text-text-muted">{detail}</p>
        <a
          href={fileUrl(fileId)}
          className="mt-1 inline-flex items-center gap-1 text-body-sm text-primary underline-offset-4 hover:underline"
        >
          <FileText className="size-4" aria-hidden="true" />
          <span className="truncate">{fileName}</span>
        </a>
      </div>
      <div className="flex items-center gap-2">
        <StatusBadge status={status} reason={reason} />
        <ConfirmDialog
          trigger={
            <IconButton aria-label={`Delete ${title}`}>
              <Trash2 />
            </IconButton>
          }
          title={`Delete “${title}”?`}
          description="It’s removed from your profile together with its file."
          confirmLabel="Delete"
          onConfirm={onDelete}
        />
      </div>
    </li>
  );
}

export function CertificatesCard() {
  const qc = useQueryClient();
  const list = useCertificates();
  const remove = useDeleteCertificate();
  const up = useUploadState();
  const form = useForm<CertificateValues>({
    resolver: zodResolver(certificateSchema),
    defaultValues: { title: "", issuer: "" },
  });
  const submit = form.handleSubmit(async (values) => {
    if (!up.file) {
      up.setFileError("Choose the certificate file.");
      return;
    }
    up.setProgress(0);
    try {
      await uploadCertificate(values, up.file, up.setProgress);
      await qc.invalidateQueries({ queryKey: keys.certificates });
      toast({
        tone: "success",
        title: "Certificate uploaded",
        description: "An admin will verify it.",
      });
      form.reset();
      up.done();
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["title", "issuer"])) up.setFileError(messageFor(e));
    } finally {
      up.setProgress(null);
    }
  });

  return (
    <Card>
      <CardHeader
        title="Certificates"
        description="Courses and exams you passed. Verified certificates appear on your public profile."
      />
      {list.isPending ? (
        <div className="space-y-2 p-5">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      ) : list.isError ? (
        <ErrorState onRetry={() => void list.refetch()} />
      ) : list.data.length ? (
        <ul className="divide-y divide-border">
          {list.data.map((c) => (
            <EvidenceRow
              key={c.id}
              title={c.title}
              detail={`Issued by ${c.issuer}, added ${formatDate(c.created_at)}`}
              fileId={c.file.id}
              fileName={c.file.name}
              status={c.status}
              reason={c.reason}
              onDelete={async () => {
                await remove.mutateAsync(c.id);
                toast({ tone: "success", title: "Certificate deleted" });
              }}
            />
          ))}
        </ul>
      ) : null}
      <form
        noValidate
        onSubmit={(e) => void submit(e)}
        className="grid gap-4 border-t border-border p-5 md:grid-cols-2"
      >
        <Field
          label="Certificate"
          required
          placeholder="AWS Cloud Practitioner"
          error={form.formState.errors.title?.message}
          {...form.register("title")}
        />
        <Field
          label="Issued by"
          required
          placeholder="Amazon Web Services"
          error={form.formState.errors.issuer?.message}
          {...form.register("issuer")}
        />
        <div className="md:col-span-2">
          <FileDropzone
            label="Certificate file"
            rule={CERTIFICATE_RULE}
            progress={up.progress}
            error={up.fileError}
            resetKey={up.reset}
            onFile={(f) => {
              up.setFile(f);
              up.setFileError(undefined);
            }}
          />
        </div>
        <div>
          <Button type="submit" variant="outline" loading={up.progress !== null}>
            Upload certificate
          </Button>
        </div>
      </form>
    </Card>
  );
}

function reviewDetail(r: ExternalReview): string {
  return `${formatScore(Number(r.rating_norm))} / 100 on ${r.source}, project ended ${formatDate(r.project_date)}`;
}

export function ExternalReviewsCard() {
  const qc = useQueryClient();
  const list = useExternalReviews();
  const remove = useDeleteExternalReview();
  const up = useUploadState();
  const form = useForm<ReviewValues>({
    resolver: zodResolver(reviewSchema),
    defaultValues: { source: "", rating: "", scale: "5", project_date: "" },
  });
  const submit = form.handleSubmit(async (values) => {
    if (!up.file) {
      up.setFileError("Choose a screenshot or export of the review.");
      return;
    }
    up.setProgress(0);
    try {
      await uploadExternalReview(
        {
          source: values.source,
          rating: String(values.rating),
          scale: String(values.scale),
          project_date: values.project_date,
        },
        up.file,
        up.setProgress,
      );
      await qc.invalidateQueries({ queryKey: keys.reviews });
      toast({
        tone: "success",
        title: "Review added",
        description: "An admin will check the evidence.",
      });
      form.reset();
      up.done();
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["source", "rating", "scale", "project_date"]))
        up.setFileError(messageFor(e));
    } finally {
      up.setProgress(null);
    }
  });
  const errors = form.formState.errors;

  return (
    <Card>
      <CardHeader
        title="Reviews from other platforms"
        description="Bring ratings from Upwork, Fiverr and similar sites. Once verified, they help your reputation."
      />
      {list.isPending ? (
        <div className="space-y-2 p-5">
          <Skeleton className="h-14" />
        </div>
      ) : list.isError ? (
        <ErrorState onRetry={() => void list.refetch()} />
      ) : list.data.length ? (
        <ul className="divide-y divide-border">
          {list.data.map((r) => (
            <EvidenceRow
              key={r.id}
              title={r.source}
              detail={reviewDetail(r)}
              fileId={r.file.id}
              fileName={r.file.name}
              status={r.status}
              reason={r.reason}
              onDelete={async () => {
                await remove.mutateAsync(r.id);
                toast({ tone: "success", title: "Review deleted" });
              }}
            />
          ))}
        </ul>
      ) : null}
      <form
        noValidate
        onSubmit={(e) => void submit(e)}
        className="grid gap-4 border-t border-border p-5 sm:grid-cols-2 lg:grid-cols-4"
      >
        <Field
          label="Platform"
          required
          placeholder="Upwork"
          error={errors.source?.message}
          {...form.register("source")}
        />
        <Field
          label="Rating"
          required
          type="number"
          inputMode="decimal"
          step="0.1"
          min={0}
          error={errors.rating?.message}
          {...form.register("rating")}
        />
        <Field
          label="Out of"
          required
          type="number"
          inputMode="numeric"
          min={1}
          max={100}
          error={errors.scale?.message}
          {...form.register("scale")}
        />
        <Field
          label="Project ended"
          required
          type="date"
          error={errors.project_date?.message}
          {...form.register("project_date")}
        />
        <div className="sm:col-span-2 lg:col-span-4">
          <FileDropzone
            label="Evidence"
            rule={REVIEW_RULE}
            progress={up.progress}
            error={up.fileError}
            resetKey={up.reset}
            onFile={(f) => {
              up.setFile(f);
              up.setFileError(undefined);
            }}
          />
        </div>
        <div>
          <Button type="submit" variant="outline" loading={up.progress !== null}>
            Add review
          </Button>
        </div>
      </form>
    </Card>
  );
}
