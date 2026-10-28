/**
 * One assessment question (role assessment spec §11.3): the text, an optional code block (plain
 * text, monospace — never HTML), four large option cards (keys 1–4 choose, Enter confirms) and
 * "Confirm answer" / "Skip". There is no way back: a confirmed or skipped question is locked
 * (§6.4), and a skip asks first. Copying the question is discouraged (§7.6) without getting in
 * the way of screen readers, zoom or the keyboard.
 */
import { useEffect, useRef, useState } from "react";
import type { AssessmentQuestion } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { RadioGroup } from "@/components/ui/Choice";
import { ConfirmDialog } from "@/components/ui/Overlay";
import { inlineCode } from "@/lib/inlineCode";

const LETTERS = ["A", "B", "C", "D"] as const;

export function CodeBlock({ code }: { code: string }) {
  return (
    // Long lines wrap rather than scroll: on a phone the whole snippet stays in view during a
    // timed question, and there's no scroll region a keyboard can't reach.
    <pre className="whitespace-pre-wrap break-words rounded-lg border border-border bg-surface-2 p-4 font-mono text-body-sm leading-relaxed text-text">
      <code>{code.replace(/\n$/, "")}</code>
    </pre>
  );
}

function noCopy(event: Event) {
  event.preventDefault();
}

export function QuestionView({
  question,
  busy,
  onAnswer,
}: {
  question: AssessmentQuestion;
  busy: boolean;
  onAnswer: (choice: number | null) => void;
}) {
  const [choice, setChoice] = useState<string>("");
  const heading = useRef<HTMLHeadingElement>(null);
  const area = useRef<HTMLDivElement>(null);

  // Copying and the context menu are speed bumps only (§7.6): native listeners on this area,
  // so nothing changes for keyboard, zoom or assistive technology.
  useEffect(() => {
    const node = area.current;
    if (!node) return undefined;
    for (const type of ["copy", "cut", "contextmenu"]) node.addEventListener(type, noCopy);
    return () => {
      for (const type of ["copy", "cut", "contextmenu"]) node.removeEventListener(type, noCopy);
    };
  }, []);

  // A new question: clear the choice and move focus to it (screen readers hear it first).
  useEffect(() => {
    setChoice("");
    heading.current?.focus();
  }, [question.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (busy || event.altKey || event.ctrlKey || event.metaKey) return;
      const n = Number(event.key);
      if (n >= 1 && n <= question.options.length) {
        setChoice(String(n - 1));
        event.preventDefault();
      } else if (event.key === "Enter" && choice !== "") {
        const target = event.target as HTMLElement | null;
        if (target?.tagName === "BUTTON") return; // the focused button handles its own Enter
        onAnswer(Number(choice));
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [busy, choice, onAnswer, question.options.length]);

  return (
    <section aria-labelledby={`q-${question.id}`} className="flex flex-col gap-5">
      <div ref={area} className="select-none space-y-4" data-testid="question">
        {question.competency ? (
          <p className="text-body-sm text-text-muted">{question.competency}</p>
        ) : null}
        <h2
          id={`q-${question.id}`}
          ref={heading}
          tabIndex={-1}
          className="text-lead font-semibold text-text outline-none sm:text-h4"
        >
          {inlineCode(question.text)}
        </h2>
        {question.code_snippet ? <CodeBlock code={question.code_snippet} /> : null}
        <RadioGroup
          key={question.id}
          cards
          hideLegend
          legend="Your answer"
          value={choice}
          onValueChange={setChoice}
          options={question.options.map((text, i) => ({
            value: String(i),
            label: (
              <span className="flex gap-3">
                <span className="font-semibold text-text-muted tabular" aria-hidden="true">
                  {LETTERS[i]}
                </span>
                <span className="text-body text-text">{inlineCode(text)}</span>
              </span>
            ),
          }))}
        />
      </div>
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        <ConfirmDialog
          trigger={
            <Button variant="outline" disabled={busy}>
              Skip
            </Button>
          }
          title="Skip this question?"
          description="You can’t come back to it, and it counts as a wrong answer."
          confirmLabel="Skip question"
          destructive={false}
          onConfirm={() => {
            onAnswer(null);
          }}
        />
        <Button
          loading={busy}
          disabled={choice === ""}
          onClick={() => {
            onAnswer(Number(choice));
          }}
        >
          Confirm answer
        </Button>
      </div>
      <p className="hidden text-caption text-text-muted sm:block">
        Keys 1–4 choose an answer; Enter confirms it.
      </p>
    </section>
  );
}
