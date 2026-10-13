/**
 * Файл календаря (.ics) для матча.
 *
 * Время матча известно как московское; в календарь оно записывается в UTC
 * (DTSTART:...Z), поэтому попадает в правильный момент у зрителя из любого
 * часового пояса. Строки складываются по 75 октетов, как требует RFC 5545.
 */

const LINE_LIMIT_OCTETS = 75;
const encoder = new TextEncoder();

export function escapeIcsText(value) {
  return String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/;/g, "\\;")
    .replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n");
}

export function foldIcsLine(line) {
  const text = String(line);
  if (encoder.encode(text).length <= LINE_LIMIT_OCTETS) {
    return text;
  }

  const chunks = [];
  let current = "";
  let currentBytes = 0;
  let limit = LINE_LIMIT_OCTETS;

  for (const char of text) {
    const bytes = encoder.encode(char).length;
    if (currentBytes + bytes > limit) {
      chunks.push(current);
      current = "";
      currentBytes = 0;
      limit = LINE_LIMIT_OCTETS - 1; // продолжение начинается с пробела
    }
    current += char;
    currentBytes += bytes;
  }
  chunks.push(current);

  return chunks.join("\r\n ");
}

/** Дата-время в формате UTC: 20261017T081500Z. */
function utcStamp(date) {
  return date.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
}

/**
 * @param {{id:number,date:string,datetime:Date,home:string,away:string,time?:string,group?:string,tournament?:string,tour?:string}} match
 */
export function buildIcs(match, { uidDomain = "centr-hockey", durationMinutes = 90, now = new Date() } = {}) {
  const start = match?.datetime;
  if (!(start instanceof Date) || Number.isNaN(start.getTime())) {
    throw new Error("buildIcs: match.datetime is required");
  }

  const end = new Date(start.getTime() + durationMinutes * 60000);
  const descriptionParts = [match.tournament, match.group, match.tour].map((part) => String(part ?? "").trim()).filter(Boolean);

  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Centr 2016//Hockey onepager//RU",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:centr2016-${match.id || match.date.replace(/-/g, "")}@${uidDomain}`,
    `DTSTAMP:${utcStamp(now)}`,
    `DTSTART:${utcStamp(start)}`,
    `DTEND:${utcStamp(end)}`,
    `SUMMARY:${escapeIcsText(`${match.home} — ${match.away}`)}`,
  ];

  if (descriptionParts.length) {
    lines.push(`DESCRIPTION:${escapeIcsText(descriptionParts.join(", "))}`);
  }

  lines.push("END:VEVENT", "END:VCALENDAR");

  return `${lines.map(foldIcsLine).join("\r\n")}\r\n`;
}
