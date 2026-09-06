/* Shared display formatting for Meridian workspaces. */

/* Parse a date value WITHOUT the UTC/local one-day shift that affects date-only
   strings like "2026-09-16". `new Date("2026-09-16")` is parsed as UTC midnight,
   which renders as the prior day in any UTC-negative timezone. Treat date-only
   values as local midnight so the displayed day is the day the API meant.
   Full timestamps ("2026-09-16T12:00:00Z") still parse normally. */
export function parseLocalDate(value) {
  if (!value) {
    return null;
  }
  // Date-only ISO "2026-09-16".
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return parseDateOnly(new Date(`${value}T12:00:00`));
  }
  // A calendar date expressed as midnight UTC (e.g. "Wed, 16 Sep 2026 00:00:00 GMT"
  // from the API) also shifts a day earlier in a UTC-negative timezone. Detect an
  // all-zero time and re-parse from the UTC calendar date so the displayed day is
  // the API's (Sep 16), not the local-shifted prior day (Sep 15).
  if (/00:00:00/i.test(value)) {
    const asDate = new Date(value);
    if (!Number.isNaN(asDate.getTime())) {
      return new Date(
        asDate.getUTCFullYear(),
        asDate.getUTCMonth(),
        asDate.getUTCDate(),
        12,
      );
    }
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function parseDateOnly(parsed) {
  // Return the same calendar day but at local noon (avoids any DST/zone shift).
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate(), 12);
}

export function formatCurrency(amount, currency) {
  const code = currency || "USD";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
    }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

export function dayKey(isoTimestamp) {
  const parsed = new Date(isoTimestamp);
  if (Number.isNaN(parsed.getTime())) {
    return "unknown";
  }
  const parts = [
    parsed.getFullYear(),
    String(parsed.getMonth() + 1).padStart(2, "0"),
    String(parsed.getDate()).padStart(2, "0"),
  ];
  return parts.join("-");
}

export function dayLabel(isoTimestamp) {
  const parsed = new Date(isoTimestamp);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown date";
  }
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDay = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const dayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfDay.getTime() - startOfToday.getTime()) / dayMs);
  if (diffDays === 0) {
    return "Today";
  }
  if (diffDays === -1) {
    return "Yesterday";
  }
  return parsed.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}
