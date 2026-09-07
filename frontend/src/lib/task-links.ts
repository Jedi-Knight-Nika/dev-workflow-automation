export type TextPart = { text: string; href?: string; label?: string };

export function safeExternalUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function taskDescriptionParts(description: string, sourceUrl?: string | null): TextPart[] {
  const text = description
    .split('\n')
    .filter((line) => {
      const match = line.trim().match(/^[\w -]+:\s*(https?:\/\/\S+)$/);
      return !match || !sourceUrl || safeExternalUrl(match[1]) !== safeExternalUrl(sourceUrl);
    })
    .join('\n')
    .trim();
  const parts: TextPart[] = [];
  const pattern = /https?:\/\/[^\s<>"']+/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index;
    const candidate = match[0].replace(/[.,;!?]+$/, '');
    const href = safeExternalUrl(candidate);
    if (!href) continue;
    parts.push({ text: text.slice(cursor, start) });
    parts.push({ text: candidate, href, label: new URL(href).hostname.replace(/^www\./, '') });
    cursor = start + candidate.length;
  }
  parts.push({ text: text.slice(cursor) });
  return parts.filter((part) => part.text.length > 0);
}
