/**
 * Team comparison (spec §9.6, §13.3): the top three distinct teams side by side: score, price,
 * finish, newcomers and average competency and teamwork. A table from 768 px, a card list on
 * phones. The recommended team is marked with a badge (icon + text).
 */
import type { TeamOption } from "@/api/types";
import { Badge } from "@/components/ui/Display";
import { formatDays, formatMoney, formatScore } from "@/lib/format";

function name(i: number) {
  return i === 0 ? "Best team" : `Option ${String(i + 1)}`;
}

export function TeamComparison({
  teams,
  names,
}: {
  teams: readonly TeamOption[];
  /** Bid id → developer name, for the members of each team. */
  names: ReadonlyMap<string, string>;
}) {
  const members = (t: TeamOption) =>
    t.bid_ids.map((b) => names.get(b) ?? "Another bidder").join(", ");
  return (
    <>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-body-sm">
          <caption className="sr-only">The best teams found, side by side</caption>
          <thead>
            <tr className="border-b border-border text-left text-text-muted">
              <th scope="col" className="py-2 pr-4 font-medium">
                Team
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Score
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Price
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Finish
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Newcomers
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium">
                Competency
              </th>
              <th scope="col" className="py-2 pl-3 text-right font-medium">
                Teamwork
              </th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t, i) => (
              <tr key={t.bid_ids.join()} className="border-b border-border align-top last:border-0">
                <th scope="row" className="py-3 pr-4 text-left font-normal">
                  <span className="flex flex-wrap items-center gap-2 font-medium text-text">
                    {name(i)}
                    {t.recommended ? <Badge tone="success">Recommended</Badge> : null}
                  </span>
                  <span className="mt-1 block text-caption text-text-muted">{members(t)}</span>
                </th>
                <td className="px-3 py-3 text-right tabular text-text">{t.fitness.toFixed(2)}</td>
                <td className="px-3 py-3 text-right tabular text-text">
                  {formatMoney(t.price_paisa)}
                </td>
                <td className="px-3 py-3 text-right tabular text-text">{formatDays(t.max_days)}</td>
                <td className="px-3 py-3 text-right tabular text-text">{t.newcomers}</td>
                <td className="px-3 py-3 text-right tabular text-text">
                  {formatScore(t.mean_competency)}
                </td>
                <td className="py-3 pl-3 text-right tabular text-text">
                  {formatScore(t.mean_teamwork)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-3 md:hidden">
        {teams.map((t, i) => (
          <li key={t.bid_ids.join()} className="rounded-lg border border-border p-4">
            <p className="flex flex-wrap items-center gap-2 font-medium text-text">
              {name(i)}
              {t.recommended ? <Badge tone="success">Recommended</Badge> : null}
            </p>
            <p className="mt-1 text-caption text-text-muted">{members(t)}</p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-body-sm">
              <dt className="text-text-muted">Score</dt>
              <dd className="text-right tabular text-text">{t.fitness.toFixed(2)}</dd>
              <dt className="text-text-muted">Price</dt>
              <dd className="text-right tabular text-text">{formatMoney(t.price_paisa)}</dd>
              <dt className="text-text-muted">Finish</dt>
              <dd className="text-right tabular text-text">{formatDays(t.max_days)}</dd>
              <dt className="text-text-muted">Newcomers</dt>
              <dd className="text-right tabular text-text">{t.newcomers}</dd>
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
