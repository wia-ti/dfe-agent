// .opencode/rag/lib/chunker.ts
// Chunker sentence-aware com alvo de 200-300 tokens (~800-1200 chars PT/EN).
// Respeita fronteiras de sentenca e adiciona overlap de ~50 tokens entre chunks.

const TARGET_MIN_CHARS: number = 800;
const TARGET_MAX_CHARS: number = 1200;
const OVERLAP_CHARS: number = 200;

const SENTENCE_BOUNDARIES: RegExp = /(?<=[.!?;:\n])\s+(?=[A-Z\u00C0-\u00DC])/g;
const WHITESPACE_RUN: RegExp = /\s+/g;
const SECTION_HEADING: RegExp = /^(#{1,6})\s+(.+)$/gm;

export interface Chunk {
  index: number;
  text: string;
}

function normalizeWhitespace(text: string): string {
  return text.replace(WHITESPACE_RUN, " ").trim();
}

function splitSentences(paragraph: string): string[] {
  const normalized = paragraph.trim();
  if (!normalized) {
    return [];
  }
  const parts = normalized.split(SENTENCE_BOUNDARIES);
  return parts.map((p) => p.trim()).filter((p) => p.length > 0);
}

function splitSections(text: string): string[] {
  const matches: { start: number; heading: string }[] = [];
  let m: RegExpExecArray | null;
  const re = new RegExp(SECTION_HEADING.source, "gm");
  while ((m = re.exec(text)) !== null) {
    matches.push({ start: m.index, heading: m[0] });
  }
  if (matches.length === 0) {
    return [text];
  }
  const sections: string[] = [];
  for (let i = 0; i < matches.length; i++) {
    const start = matches[i].start;
    const end = i + 1 < matches.length ? matches[i + 1].start : text.length;
    sections.push(text.slice(start, end));
  }
  if (matches[0].start > 0) {
    sections.unshift(text.slice(0, matches[0].start));
  }
  return sections;
}

function splitParagraphs(text: string): string[] {
  return text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

export function chunkText(text: string): Chunk[] {
  const cleaned = text.replace(/\r\n/g, "\n").trim();
  if (!cleaned) {
    return [];
  }

  const sections = splitSections(cleaned);
  const chunks: Chunk[] = [];
  let buffer = "";

  const flush = (): void => {
    if (buffer.trim().length === 0) {
      return;
    }
    chunks.push({ index: chunks.length, text: buffer.trim() });
    const tail = buffer.slice(-OVERLAP_CHARS);
    buffer = tail;
  };

  for (const section of sections) {
    const paragraphs = splitParagraphs(section);
    for (const para of paragraphs) {
      const sentences = splitSentences(para);
      for (const sentence of sentences) {
        const candidate = buffer.length === 0 ? sentence : buffer + " " + sentence;
        if (candidate.length > TARGET_MAX_CHARS && buffer.length >= TARGET_MIN_CHARS) {
          flush();
          buffer = (chunks.length > 0 ? chunks[chunks.length - 1].text.slice(-OVERLAP_CHARS) : "") + " " + sentence;
          continue;
        }
        if (candidate.length > TARGET_MAX_CHARS && buffer.length > 0) {
          flush();
          buffer = sentence;
          continue;
        }
        buffer = candidate;
      }
      if (buffer.length >= TARGET_MIN_CHARS) {
        flush();
      } else {
        buffer += "\n\n";
      }
    }
  }

  if (buffer.trim().length > 0) {
    chunks.push({ index: chunks.length, text: normalizeWhitespace(buffer) });
  }

  return chunks.filter((c) => c.text.length > 0);
}