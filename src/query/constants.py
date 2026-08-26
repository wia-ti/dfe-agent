from __future__ import annotations

MIN_RELEVANCE_SCORE: float = 0.5
DEFAULT_TOP_K: int = 5

# --- Boost temporal (frescor) ---
# Peso do componente de recencia no score final (0.0 = so semantica, 1.0 = so recencia).
# 0.3 significa: 70% score semantico + 30% recencia. Default conservador para
# nao penalizar NTs historicas relevantes quando a pergunta nao envolve prazo.
RECENCY_WEIGHT: float = 0.3

# Meia-vida em dias para o decaimento exponencial da recencia.
# Apos N dias, o score de recencia cai a 50% (com half_life=180, ~50% em 6 meses).
# Documentos muito antigos (>= 5x half_life) tem recencia ~0.
RECENCY_HALF_LIFE_DAYS: float = 180.0

# Quantos chunks candidatos puxar do VectorStore antes de aplicar dedup por
# documento + boost temporal. Multiplos chunks do mesmo doc sao colapsados em
# apenas o melhor. Multiplo de top_k * 3 e suficiente na pratica.
MAX_CANDIDATES_PER_QUERY: int = 30

# --- Busca hibrida (Fase 11) ---
# Constante de smoothing da fusao Reciprocal Rank Fusion:
#   score_rrf(d) = sum_fontes 1 / (k + rank_d + 1)
# ``k=60`` e o default classico do paper original; valores menores dao mais
# peso aos primeiros colocados das listas.
HYBRID_RRF_K: int = 60

# --- Retrieval hierarquico (Fase 12) ---
# Quantos documentos sao selecionados no primeiro estagio (cosine contra
# embeddings dos summaries) antes de puxar os chunks detalhados.
# 10 e um trade-off: cobre 10 NTs recentes o suficiente para responder
# perguntas tipicas sem inflar a busca do segundo estagio.
HIERARCHICAL_TOP_DOCS: int = 10

# --- Re-ranking cross-encoder (Fase 15) ---
# Re-ranking e opt-in (default OFF): adiciona latencia e raramente
# melhora recall@5 de forma mensuravel. Ative via ``--rerank`` no CLI.
RERANK_DEFAULT: bool = False
RERANK_CANDIDATES_MULTIPLIER: int = 5  # top_k * 5 candidatos antes do rerank