/** Skills with self-assessed levels (spec §7.2, §13.5 #15). Each change saves at once; a
 * verified test score sits next to the skill it proves. */
import { useState } from "react";
import { Link } from "react-router";
import type { DeveloperSkill, Skill, SkillTest } from "@/api/types";
import { Checkbox } from "@/components/ui/Choice";
import { Badge, Card, CardHeader } from "@/components/ui/Display";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { toast } from "@/components/ui/toast-store";
import { messageFor } from "@/features/auth/errors";
import { formatScore } from "@/lib/format";
import { useReplaceSkills } from "./api";
import { SaveIndicator } from "./AboutCard";
import type { SaveState } from "./useAutosave";

const LEVELS = [
  { value: "1", label: "1" },
  { value: "2", label: "2" },
  { value: "3", label: "3" },
  { value: "4", label: "4" },
  { value: "5", label: "5" },
] as const;
type Level = (typeof LEVELS)[number]["value"];

export function SkillsCard({
  skills,
  mine,
  tests,
}: {
  skills: Skill[];
  mine: DeveloperSkill[];
  tests: SkillTest[] | undefined;
}) {
  const replace = useReplaceSkills();
  const [state, setState] = useState<SaveState>("idle");
  const [pending, setPending] = useState<Map<string, number> | null>(null);
  const levels = pending ?? new Map(mine.map((s) => [s.skill_id, s.self_level]));

  const save = async (next: Map<string, number>) => {
    setPending(next);
    setState("saving");
    try {
      await replace.mutateAsync(
        [...next].map(([skill_id, self_level]) => ({ skill_id, self_level })),
      );
      setState("saved");
      setPending(null);
    } catch (e) {
      setState("error");
      setPending(null);
      toast({ tone: "danger", title: "Skills not saved", description: messageFor(e) });
    }
  };

  const toggle = (id: string, on: boolean) => {
    const next = new Map(levels);
    if (on) next.set(id, 3);
    else next.delete(id);
    void save(next);
  };
  const setLevel = (id: string, level: number) => {
    const next = new Map(levels);
    next.set(id, level);
    void save(next);
  };

  return (
    <Card>
      <CardHeader
        title="Skills"
        description="Rate yourself from 1 (learning) to 5 (expert). A passed skill test shows as verified."
        action={<SaveIndicator state={state} onRetry={() => void save(levels)} />}
      />
      <ul className="divide-y divide-border">
        {skills.map((skill) => {
          const level = levels.get(skill.id);
          const test = tests?.find((t) => t.skill_id === skill.id);
          return (
            <li
              key={skill.id}
              className="flex flex-col gap-3 px-5 py-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
                <Checkbox
                  label={skill.name}
                  checked={level !== undefined}
                  onCheckedChange={(v) => {
                    toggle(skill.id, v === true);
                  }}
                />
                {test?.last_score != null ? (
                  <Badge tone="success">
                    Verified: {formatScore(Number(test.last_score))} / 100
                  </Badge>
                ) : test && level !== undefined ? (
                  <Link
                    to="/dev/challenges"
                    className="text-body-sm text-primary underline-offset-4 hover:underline"
                  >
                    Take the {skill.name} test
                  </Link>
                ) : null}
              </div>
              {level !== undefined ? (
                <SegmentedControl<Level>
                  size="sm"
                  label={`${skill.name} level`}
                  value={String(level) as Level}
                  onChange={(v) => {
                    setLevel(skill.id, Number(v));
                  }}
                  segments={LEVELS}
                />
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
