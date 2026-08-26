// .opencode/rag/lib/classifier.ts
// Classificador heuristico de paragrafos em 4 categorias do sistema:
//   bug_root_cause        -- bug resolvido com causa raiz
//   architecture_decision -- decisao de arquitetura e o porquê
//   team_pattern          -- padrao adotado pelo time
//   what_didnt_work       -- o que nao funcionou e por quê
//
// Implementacao: scoring baseado em palavras-chave + sinais estruturais
// (presenca de "porque", "razao", "decidimos", etc). Nao usa LLM -- precisa
// rodar em hook async sem bloquear o agent.

export type Category =
  | "bug_root_cause"
  | "architecture_decision"
  | "team_pattern"
  | "what_didnt_work";

export const CATEGORIES: readonly Category[] = [
  "bug_root_cause",
  "architecture_decision",
  "team_pattern",
  "what_didnt_work",
] as const;

export const CATEGORY_LABELS: Record<Category, string> = {
  bug_root_cause: "Bugs resolvidos com causa raiz",
  architecture_decision: "Decisoes de arquitetura e o porquê",
  team_pattern: "Padroes adotados pelo time",
  what_didnt_work: "O que nao funcionou e por quê",
};

interface CategoryProfile {
  category: Category;
  positive: RegExp[];
  negative: RegExp[];
  weight: number;
}

const PROFILES: CategoryProfile[] = [
  {
    category: "bug_root_cause",
    weight: 1.0,
    positive: [
      /\b(bug|defeito|erro)\b/i,
      /\b(causa\s+raiz|root\s+cause|fonte\s+do\s+erro)\b/i,
      /\b(resolv[iu]do|corrigid[oa]|fix(ou|ed))\b/i,
      /\b(off-?by-?one|npe|null\s+pointer|stack\s+overflow|race\s+condition)\b/i,
    ],
    negative: [
      /\b(nao\s+vamos|nunca|futuramente)\b/i,
    ],
  },
  {
    category: "architecture_decision",
    weight: 1.0,
    positive: [
      /\b(arquitetur[ao]|architecture|design\s+decision)\b/i,
      /\b(decid(iu|imos)|optamos|escolhemos|adotamos)\b/i,
      /\b(porque|por\s+que|pois|motivo|razao|justificativ[ao])\b/i,
      /\b(vantagem|trade-?off|compromisso)\b/i,
      /\b(spring|sqlite|fastapi|react|postgres|mongo)\b/i,
    ],
    negative: [],
  },
  {
    category: "team_pattern",
    weight: 1.0,
    positive: [
      /\b(padrao|pattern|conve[nc][aã]o|convencao)\b/i,
      /\b(sempre|regra\s+do\s+time|politica)\b/i,
      /\b(naming\s+convention|type\s+hint|test(ing|e))\b/i,
      /\b(nosso\s+c(odigo|ódigo)|na\s+base|aqui\s+no\s+projeto)\b/i,
      /\b(snake_case|kebab-case|camelCase)\b/i,
    ],
    negative: [],
  },
  {
    category: "what_didnt_work",
    weight: 1.0,
    positive: [
      /\b(nao\s+funcion[ou]|deu\s+errad[oa]|falhou)\b/i,
      /\b(abandonamos|desistimos|voltamos\s+atras)\b/i,
      /\b(tentamos|experimentamos|testamos)\b/i,
      /\b(anti[- ]pattern|armadilha|gotcha)\b/i,
      /\b(mais\s+lento|nao\s+escala|muito\s+complex[oa])\b/i,
    ],
    negative: [],
  },
];

export interface ClassifiedSection {
  category: Category;
  content: string;
}

function scoreSection(text: string, profile: CategoryProfile): number {
  let score = 0;
  for (const pattern of profile.positive) {
    const matches = text.match(new RegExp(pattern.source, "gi"));
    if (matches) {
      score += matches.length;
    }
  }
  for (const pattern of profile.negative) {
    const matches = text.match(new RegExp(pattern.source, "gi"));
    if (matches) {
      score -= matches.length * 0.5;
    }
  }
  return score * profile.weight;
}

export function classifySection(text: string): Category {
  let bestScore = 0;
  let bestCategory: Category = "team_pattern";
  for (const profile of PROFILES) {
    const s = scoreSection(text, profile);
    if (s > bestScore) {
      bestScore = s;
      bestCategory = profile.category;
    }
  }
  return bestCategory;
}

export function splitMarkdownSections(md: string): { heading: string; body: string }[] {
  const lines = md.split(/\r?\n/);
  const sections: { heading: string; body: string }[] = [];
  let currentHeading = "(sem categoria)";
  let currentBody: string[] = [];

  const flush = (): void => {
    const body = currentBody.join("\n").trim();
    if (body.length > 0 || currentHeading !== "(sem categoria)") {
      sections.push({ heading: currentHeading, body });
    }
    currentBody = [];
  };

  for (const line of lines) {
    const headingMatch = line.match(/^#{2,3}\s+(.+)$/);
    if (headingMatch) {
      flush();
      currentHeading = headingMatch[1].trim();
    } else {
      currentBody.push(line);
    }
  }
  flush();

  return sections.filter((s) => s.body.length > 20);
}

export function classifyMarkdown(md: string): ClassifiedSection[] {
  const sections = splitMarkdownSections(md);
  return sections.map((s) => ({
    category: classifySection(s.heading + "\n" + s.body),
    content: `## ${s.heading}\n\n${s.body}`.trim(),
  }));
}

export function agentToCategory(agentName: string): Category | null {
  const normalized = agentName.toLowerCase();
  if (normalized.includes("backend")) {
    return "architecture_decision";
  }
  if (normalized.includes("qa") || normalized.includes("test")) {
    return "what_didnt_work";
  }
  if (normalized.includes("ml") || normalized.includes("prompt")) {
    return "team_pattern";
  }
  if (normalized.includes("debug") || normalized.includes("fix")) {
    return "bug_root_cause";
  }
  return null;
}