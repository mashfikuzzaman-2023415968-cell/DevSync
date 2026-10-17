/** "Good morning / afternoon / evening" by the hour in Asia/Dhaka (spec §13.1: times shown
 * in Dhaka time). */
export function greeting(now: Date = new Date()): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "Asia/Dhaka",
    }).format(now),
  );
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function firstName(displayName: string | undefined): string {
  return displayName?.trim().split(/\s+/)[0] ?? "";
}
