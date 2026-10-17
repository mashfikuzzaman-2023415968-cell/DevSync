/**
 * Sample data for the homepage illustrations (spec §13.11 #5: "real components with seeded
 * sample data"). Every value comes from the demo seed in spec §18.2 and §18.4, never invented
 * (rule 0.2.6); `sample.test.ts` recomputes the CPM figures so they cannot drift.
 * Algorithm results (teams, cost of fairness) are NOT here: they arrive from a real run in
 * Phase 7 (DECISIONS D21).
 */

export interface SampleMilestone {
  id: string;
  name: string;
  days: number;
  after: string[];
}

/** "Online ordering system" (§18.2 #1): budget ৳120,000, deadline 30 days, team of 4. */
export const orderingSystem = {
  title: "Online ordering system",
  budgetPaisa: 120_000 * 100,
  deadlineDays: 30,
  skills: ["React", "FastAPI", "PostgreSQL", "Testing"],
  milestones: [
    { id: "req", name: "Requirements & design", days: 4, after: [] },
    { id: "db", name: "Database", days: 5, after: ["req"] },
    { id: "api", name: "Backend API", days: 8, after: ["db"] },
    { id: "fe", name: "Frontend", days: 9, after: ["req"] },
    { id: "int", name: "Integration", days: 3, after: ["api", "fe"] },
    { id: "qa", name: "Testing & launch", days: 4, after: ["int"] },
  ] satisfies SampleMilestone[],
  /** CPM result stated in §18.2 (checked by sample.test.ts). */
  cpm: {
    durationDays: 24,
    critical: ["req", "db", "api", "int", "qa"],
    schedule: {
      req: { es: 0, ef: 4, slack: 0 },
      db: { es: 4, ef: 9, slack: 0 },
      api: { es: 9, ef: 17, slack: 0 },
      fe: { es: 4, ef: 13, slack: 4 },
      int: { es: 17, ef: 20, slack: 0 },
      qa: { es: 20, ef: 24, slack: 0 },
    } as Record<string, { es: number; ef: number; slack: number }>,
  },
} as const;

/** "Inventory dashboard" on project day 12 (§18.2 #2). */
export const inventoryDashboard = {
  title: "Inventory dashboard",
  day: 12,
  plannedDays: 23,
  forecastDays: 25,
  risks: [
    {
      severity: "CRITICAL" as const,
      title: "Dashboard frontend is late",
      detail: "It’s on the critical path, so the finish moves from day 23 to day 25.",
    },
    {
      severity: "MEDIUM" as const,
      title: "Inventory API has used its slack",
      detail: "Any further delay will push the deadline too.",
    },
    {
      severity: "MEDIUM" as const,
      title: "A team member has been inactive for 8 days",
      detail: "Message them or plan a replacement.",
    },
  ],
  milestones: [
    { name: "Requirements", progress: 100 },
    { name: "UI design", progress: 100 },
    { name: "Inventory API", progress: 70 },
    { name: "Dashboard frontend", progress: 40 },
  ],
} as const;

/** Stage-1 reputation snapshot for two seed developers (§18.4), stored 0–1.
 * expertise = ω, communication = X, teamwork = X_m, quality = β, diversity = μ, punctuality = T. */
export const reputationSample = [
  {
    name: "Arif Hossain",
    newcomer: false,
    params: {
      expertise: 0.78,
      communication: 0.86,
      teamwork: 0.77,
      quality: 0.84,
      diversity: 0.8,
      punctuality: 0.7,
    },
    competency: 0.8,
    performance: 0.8,
  },
  {
    name: "Zahid Mahmud",
    newcomer: false,
    params: {
      expertise: 0.5,
      communication: 0.62,
      teamwork: 0.55,
      quality: 0.65,
      diversity: 0.5,
      punctuality: 0.6,
    },
    competency: 0.54,
    performance: 0.6,
  },
] as const;

/** Newcomers in the seed (§18.1) with their skill-test scores. */
export const newcomers = [
  { name: "Nadia Rahman", skill: "React", score: 0.85 },
  { name: "Mehjabin Chowdhury", skill: "Testing", score: 0.9 },
  { name: "Lamia Akter", skill: "FastAPI", score: 0.75 },
] as const;
