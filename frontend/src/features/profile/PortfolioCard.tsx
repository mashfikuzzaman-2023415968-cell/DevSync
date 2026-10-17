/** Portfolio (spec §13.5 #15): up to 20 items in the order clients see them (drag, keyboard
 * or the row menu), each with up to five images. */
import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowDown,
  ArrowUp,
  ExternalLink,
  ImageOff,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { fileUrl } from "@/api/client";
import type { PortfolioItem, Skill } from "@/api/types";
import { Button, IconButton } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Choice";
import { Badge, Card, CardHeader } from "@/components/ui/Display";
import { EmptyState } from "@/components/ui/Feedback";
import { Field, FormField, Textarea } from "@/components/ui/Field";
import { FileDropzone } from "@/components/ui/FileDropzone";
import { ConfirmDialog, Dialog, DropdownMenu } from "@/components/ui/Overlay";
import { SortableList } from "@/components/ui/SortableList";
import { toast } from "@/components/ui/toast-store";
import { applyFieldErrors, messageFor } from "@/features/auth/errors";
import {
  uploadPortfolioImage,
  useCreatePortfolioItem,
  useDeletePortfolioImage,
  useDeletePortfolioItem,
  useReorderPortfolio,
  useUpdatePortfolioItem,
} from "./api";
import { useQueryClient } from "@tanstack/react-query";
import { IMAGE_RULE, itemSchema, type ItemValues } from "./schemas";
import { keys } from "./api";

export const MAX_ITEMS = 20;
export const MAX_IMAGES = 5;

function ImageManager({ item }: { item: PortfolioItem }) {
  const qc = useQueryClient();
  const remove = useDeletePortfolioImage();
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string>();
  const [done, setDone] = useState(0);
  const full = item.images.length >= MAX_IMAGES;

  const onFile = async (file: File) => {
    setError(undefined);
    setProgress(0);
    try {
      const updated = await uploadPortfolioImage(item.id, file, setProgress);
      qc.setQueryData<PortfolioItem[]>(keys.portfolio, (old) =>
        old?.map((i) => (i.id === updated.id ? updated : i)),
      );
      toast({ tone: "success", title: "Image added" });
      setDone((n) => n + 1);
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setProgress(null);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-body-sm font-medium text-text">
        Images{" "}
        <span className="font-normal text-text-muted">
          ({item.images.length} of {MAX_IMAGES})
        </span>
      </p>
      {item.images.length ? (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {item.images.map((img, i) => (
            <li key={img.id} className="relative">
              <img
                src={fileUrl(img.file.id)}
                alt={`${item.title}, screenshot ${String(i + 1)}`}
                loading="lazy"
                className="aspect-[16/10] w-full rounded-md border border-border object-cover"
              />
              <IconButton
                aria-label={`Remove image ${String(i + 1)}`}
                size="sm"
                className="absolute -right-2 -top-2 border border-border bg-surface shadow-sm"
                disabled={remove.isPending}
                onClick={() => {
                  remove.mutate(
                    { itemId: item.id, imageId: img.id },
                    {
                      onSuccess: () => toast({ tone: "success", title: "Image removed" }),
                      onError: (e) =>
                        toast({
                          tone: "danger",
                          title: "Image not removed",
                          description: messageFor(e),
                        }),
                    },
                  );
                }}
              >
                <X />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : null}
      {full ? (
        <p className="text-body-sm text-text-muted">Remove an image to add another.</p>
      ) : (
        <FileDropzone
          label="Add an image"
          rule={IMAGE_RULE}
          preview="landscape"
          progress={progress}
          error={error}
          resetKey={done}
          onFile={(f) => void onFile(f)}
        />
      )}
    </div>
  );
}

function ItemDialog({
  open,
  onOpenChange,
  item,
  skills,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: PortfolioItem | null;
  skills: Skill[];
  onCreated: (item: PortfolioItem) => void;
}) {
  const create = useCreatePortfolioItem();
  const update = useUpdatePortfolioItem();
  const form = useForm<ItemValues>({
    resolver: zodResolver(itemSchema),
    values: {
      title: item?.title ?? "",
      description: item?.description ?? "",
      url: item?.url ?? "",
      skill_ids: item?.skill_ids ?? [],
    },
  });
  const chosen = useWatch({ control: form.control, name: "skill_ids" });
  const description = useWatch({ control: form.control, name: "description" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit(async (values) => {
    const body = { ...values, url: values.url === "" ? null : values.url };
    try {
      if (item) {
        await update.mutateAsync({ id: item.id, body });
        toast({ tone: "success", title: "Item saved" });
        onOpenChange(false);
      } else {
        const created = await create.mutateAsync(body);
        if (created && !Array.isArray(created)) onCreated(created);
        toast({ tone: "success", title: "Item added", description: "Now add an image or two." });
      }
    } catch (e) {
      if (!applyFieldErrors(e, form.setError, ["title", "description", "url", "skill_ids"]))
        form.setError("root", { message: messageFor(e) });
    }
  });

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={item ? "Edit portfolio item" : "Add a portfolio item"}
      description="Real work you did: what it was, your part, and a link if it’s live."
    >
      <form id="portfolio-item" noValidate onSubmit={(e) => void submit(e)} className="space-y-4">
        <Field
          label="Title"
          required
          maxLength={120}
          error={errors.title?.message}
          {...form.register("title")}
        />
        <FormField label="What you did" error={errors.description?.message}>
          <Textarea
            counter
            maxLength={2000}
            rows={4}
            value={description}
            {...form.register("description")}
          />
        </FormField>
        <Field
          label="Link"
          type="url"
          inputMode="url"
          placeholder="https://"
          hint="Optional. A live site, an app store page or a repository."
          error={errors.url?.message}
          {...form.register("url")}
        />
        <fieldset>
          <legend className="mb-1 text-body-sm font-medium text-text">Skills used</legend>
          <div className="grid grid-cols-2 gap-x-4 sm:grid-cols-4">
            {skills.map((s) => (
              <Checkbox
                key={s.id}
                label={s.name}
                checked={chosen.includes(s.id)}
                onCheckedChange={(v) => {
                  form.setValue(
                    "skill_ids",
                    v === true ? [...chosen, s.id] : chosen.filter((x) => x !== s.id),
                    { shouldValidate: true },
                  );
                }}
              />
            ))}
          </div>
          {errors.skill_ids?.message ? (
            <p role="alert" className="text-caption font-medium text-danger">
              {errors.skill_ids.message}
            </p>
          ) : null}
        </fieldset>
        {errors.root?.message ? (
          <p role="alert" className="text-body-sm text-danger">
            {errors.root.message}
          </p>
        ) : null}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <Button
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {item ? "Close" : "Cancel"}
          </Button>
          <Button type="submit" loading={form.formState.isSubmitting}>
            {item ? "Save item" : "Add item"}
          </Button>
        </div>
      </form>
      {item ? (
        <div className="mt-6 border-t border-border pt-5">
          <ImageManager item={item} />
        </div>
      ) : null}
    </Dialog>
  );
}

export function PortfolioCard({ items, skills }: { items: PortfolioItem[]; skills: Skill[] }) {
  const reorder = useReorderPortfolio();
  const remove = useDeletePortfolioItem();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const editing = items.find((i) => i.id === editingId) ?? null;
  const names = new Map(skills.map((s) => [s.id, s.name]));

  const move = (ids: string[]) => {
    reorder.mutate(ids, {
      onError: (e) =>
        toast({ tone: "danger", title: "Order not saved", description: messageFor(e) }),
    });
  };
  const shift = (index: number, delta: number) => {
    const ids = items.map((i) => i.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    const [moved] = ids.splice(index, 1);
    if (moved) ids.splice(target, 0, moved);
    move(ids);
  };
  const openNew = () => {
    setEditingId(null);
    setOpen(true);
  };

  return (
    <Card>
      <CardHeader
        title="Portfolio"
        description={`Clients see these in this order. ${String(items.length)} of ${String(MAX_ITEMS)} items.`}
        action={
          items.length ? (
            <Button
              variant="outline"
              size="sm"
              onClick={openNew}
              disabled={items.length >= MAX_ITEMS}
              icon={<Plus aria-hidden="true" />}
            >
              Add item
            </Button>
          ) : null
        }
      />
      <div className="p-5">
        {items.length === 0 ? (
          <EmptyState
            icon={<ImageOff />}
            title="Show your first piece of work"
            description="One real project with a screenshot helps clients choose you, even before you have reviews."
            action={
              <Button onClick={openNew} icon={<Plus aria-hidden="true" />}>
                Add a portfolio item
              </Button>
            }
          />
        ) : (
          <SortableList
            items={items}
            label={(i) => i.title}
            onReorder={move}
            renderItem={(item, index) => (
              <div className="flex items-start gap-3 py-3 pr-2">
                {item.images[0] ? (
                  <img
                    src={fileUrl(item.images[0].file.id)}
                    alt=""
                    loading="lazy"
                    className="hidden aspect-[16/10] w-28 shrink-0 rounded-md border border-border object-cover sm:block"
                  />
                ) : null}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-body font-semibold text-text">{item.title}</p>
                  {item.description ? (
                    <p className="mt-0.5 line-clamp-2 text-body-sm text-text-muted">
                      {item.description}
                    </p>
                  ) : null}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {item.skill_ids.map((id) => (
                      <Badge key={id} tone="primary" icon={false}>
                        {names.get(id) ?? "Skill"}
                      </Badge>
                    ))}
                    <span className="text-caption text-text-muted">
                      {item.images.length === 1
                        ? "1 image"
                        : `${String(item.images.length)} images`}
                    </span>
                    {item.url ? (
                      <a
                        href={item.url}
                        rel="noopener noreferrer nofollow"
                        className="inline-flex items-center gap-1 text-caption text-primary underline-offset-4 hover:underline"
                      >
                        <ExternalLink className="size-3.5" aria-hidden="true" />
                        Link
                      </a>
                    ) : null}
                  </div>
                </div>
                <DropdownMenu
                  trigger={
                    <IconButton aria-label={`Actions for ${item.title}`}>
                      <MoreHorizontal />
                    </IconButton>
                  }
                  items={[
                    {
                      label: "Edit and add images",
                      icon: <Pencil />,
                      onSelect: () => {
                        setEditingId(item.id);
                        setOpen(true);
                      },
                    },
                    ...(index > 0
                      ? [
                          {
                            label: "Move up",
                            icon: <ArrowUp />,
                            onSelect: () => {
                              shift(index, -1);
                            },
                          },
                        ]
                      : []),
                    ...(index < items.length - 1
                      ? [
                          {
                            label: "Move down",
                            icon: <ArrowDown />,
                            onSelect: () => {
                              shift(index, 1);
                            },
                          },
                        ]
                      : []),
                  ]}
                />
                <ConfirmDialog
                  trigger={
                    <IconButton aria-label={`Delete ${item.title}`}>
                      <Trash2 />
                    </IconButton>
                  }
                  title={`Delete “${item.title}”?`}
                  description="The item and its images are removed from your profile. This can’t be undone."
                  confirmLabel="Delete item"
                  onConfirm={async () => {
                    await remove.mutateAsync(item.id);
                    toast({ tone: "success", title: "Item deleted" });
                  }}
                />
              </div>
            )}
          />
        )}
      </div>
      <ItemDialog
        open={open}
        onOpenChange={setOpen}
        item={editing}
        skills={skills}
        onCreated={(created) => {
          setEditingId(created.id);
        }}
      />
    </Card>
  );
}
