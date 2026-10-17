/**
 * File dropzone (spec §13.3, §17 Phase 3): drop a file or choose one; the type and size are
 * checked here for a quick answer (the server checks the content again and decides), the
 * upload progress shows as a bar, and an image gets a preview framed exactly the way it will
 * be shown (`fit` = cover crop, like the portfolio cards).
 */
import { FileUp, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type DragEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Progress } from "./Feedback";
import { IconButton } from "./Button";

export interface FileRule {
  /** MIME types the server accepts, e.g. ["image/png", "image/jpeg"]. */
  types: readonly string[];
  /** Largest size in bytes. */
  maxBytes: number;
  /** What the person may choose, in words ("PNG, JPEG or WebP up to 20 MB"). */
  description: string;
}

const MB = 1024 * 1024;

/** Why a file can't be uploaded, or null when it looks fine. */
export function checkFile(file: File, rule: FileRule): string | null {
  if (file.size === 0) return "This file is empty.";
  if (!rule.types.includes(file.type)) return `Choose ${rule.description}.`;
  if (file.size > rule.maxBytes)
    return `This file is ${(file.size / MB).toFixed(1)} MB; the limit is ${String(Math.round(rule.maxBytes / MB))} MB.`;
  return null;
}

interface FileDropzoneProps {
  label: string;
  rule: FileRule;
  onFile: (file: File) => void;
  /** 0–1 while uploading, null otherwise. */
  progress?: number | null;
  error?: string | undefined;
  disabled?: boolean;
  /** Show a preview of the chosen image in this frame shape. */
  preview?: "landscape" | "square" | false;
  /** Clear the chosen file (e.g. after a successful upload). */
  resetKey?: unknown;
  children?: ReactNode;
}

export function FileDropzone({
  label,
  rule,
  onFile,
  progress = null,
  error,
  disabled = false,
  preview = false,
  resetKey,
  children,
}: FileDropzoneProps) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const uploading = progress !== null;

  useEffect(() => {
    setChosen(null);
    setLocalError(null);
    if (input.current) input.current.value = "";
  }, [resetKey]);

  useEffect(() => {
    if (!preview || !chosen || !chosen.type.startsWith("image/")) {
      setPreviewUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(chosen);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [chosen, preview]);

  const take = (file: File | undefined) => {
    if (!file || disabled || uploading) return;
    const problem = checkFile(file, rule);
    setLocalError(problem);
    if (problem) {
      setChosen(null);
      return;
    }
    setChosen(file);
    onFile(file);
  };

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setOver(false);
    take(e.dataTransfer.files[0]);
  };

  const message = localError ?? error;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  return (
    <div className="space-y-2">
      {/* The label is the click target for the hidden input (keyboard users reach the input
          itself); dropping a file is an extra for pointer users. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => {
          setOver(false);
        }}
        onDrop={onDrop}
        data-over={over ? "" : undefined}
        className={cn(
          "flex min-h-32 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-surface px-4 py-6 text-center transition-colors duration-fast ease-standard hover:border-primary/50 hover:bg-primary-soft/40 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
          over && "border-primary bg-primary-soft",
          message && "border-danger",
          (disabled || uploading) && "cursor-not-allowed opacity-70",
        )}
      >
        <input
          ref={input}
          id={id}
          type="file"
          className="sr-only"
          accept={rule.types.join(",")}
          disabled={disabled || uploading}
          aria-describedby={message ? `${hintId} ${errorId}` : hintId}
          {...(message ? { "aria-invalid": true } : {})}
          onChange={(e) => {
            take(e.target.files?.[0]);
          }}
        />
        <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-primary">
          <FileUp className="size-5" aria-hidden="true" />
        </span>
        <span className="text-body-sm font-medium text-text">{label}</span>
        <span id={hintId} className="text-caption text-text-muted">
          Drop a file here or choose one: {rule.description}
        </span>
        {children}
      </label>
      {previewUrl && chosen ? (
        <figure className="flex items-center gap-3">
          <img
            src={previewUrl}
            alt=""
            className={cn(
              "rounded-md border border-border object-cover",
              preview === "square" ? "size-20" : "aspect-[16/10] w-32",
            )}
          />
          <figcaption className="min-w-0 flex-1 text-caption text-text-muted">
            <span className="block truncate text-body-sm text-text">{chosen.name}</span>
            Shown cropped to this frame; the full image is kept, without its location data.
          </figcaption>
          {!uploading ? (
            <IconButton
              aria-label="Remove chosen file"
              size="sm"
              onClick={() => {
                setChosen(null);
                if (input.current) input.current.value = "";
              }}
            >
              <X />
            </IconButton>
          ) : null}
        </figure>
      ) : null}
      {uploading ? <Progress value={progress * 100} label="Uploading" showValue /> : null}
      {message ? (
        <p id={errorId} role="alert" className="text-caption font-medium text-danger">
          {message}
        </p>
      ) : null}
    </div>
  );
}
