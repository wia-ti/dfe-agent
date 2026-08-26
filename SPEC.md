# SPEC.md

## Problema

O usuário, desenvolvedor/integrador de sistemas fiscais eletrônicos, precisa manter seus sistemas atualizados para emitir documentos fiscais eletrônicos (NF-e, NFC-e, CT-e, MDF-e) e manter-se a par das mudanças publicadas nos módulos do SPED e na legislação que as fundamenta (Convênios ICMS, Atos COTEPE, Ajustes SINIEF). Hoje esse trabalho é feito manualmente: acessar os portais da Secretaria da Fazenda, localizar notas técnicas e normativas em PDFs, ler/confrontar e, quando necessário, pesquisar os convênios correspondentes para dialogar com contadores. O processo é repetitivo, demorado e fragmentado em múltiplos sites.

Este projeto automatiza esse fluxo com um agente que coleta e armazena essa documentação em uma base RAG local e responde perguntas em linguagem natural, sem necessidade de navegar sites ou abrir PDFs manualmente.

## Usuários

- **Usuário único**: o próprio desenvolvedor/integrador de sistemas fiscais. Uso pessoal, sem multiusuário, autenticação ou perfis diferenciados.

## Funcionalidades

### Essenciais

1. **Coleta automática**: ao ser invocado, o agente acessa os portais oficiais e baixa todas as notas técnicas, normativas, manuais, esquemas XML, convênios e atos vinculados a NF-e, NFC-e, CT-e, MDF-e e módulos do SPED ainda não ingeridos, além de legislação correlata dos órgãos públicos habilitados.
2. **Ingestão em RAG**: o conteúdo baixado é convertido (parser PDF/HTML), quebrado em chunks e indexado em uma base RAG local em SQLite para dotar o agente de contexto.
3. **Controle de ingestão**: cada documento baixado é identificado de forma única e marcado como `ingerido` ou `não ingerido` na base SQLite. Documentos já ingeridos não são reprocessados.
4. **Garantia de atualidade**: a cada invocação, antes de responder, o agente varre os sites para identificar novos documentos e ingeri-los, de modo a sempre responder com a base mais atualizada possível.
5. **Perguntas em linguagem natural**: o usuário faz perguntas livres e recebe respostas claras, sucintas, fundamentadas em nota técnica (preferencialmente a mais atual disponível).
6. **Citação de fonte**: toda resposta é fundamentada em um documento armazenado; o agente nunca inventa informações.

### Nice-to-have

- **Qualidade de resposta**: rapidez e assertividade nas respostas como atributo contínuo de qualidade (sem SLA formal definido).

### Fora do escopo

- Emitir NF-e, NFC-e, CT-e, MDF-e ou qualquer outro documento fiscal.
- Substituir o contador ou emitir opinião legal/contábil.
- Suportar regimes tributários fora do Brasil.
- Interface mobile.
- Multiusuário, autenticação, controle de permissões ou perfis.
- Monitorar legislação não fiscal.
- Tradução para outros idiomas.
- Funcionamento offline (coleta depende de conexão).

## Módulos

| Módulo | Responsabilidade |
|---|---|
| **Agente opencode** | Orquestrador principal. Recebe a pergunta do usuário, decide o fluxo (verificar atualidade → consultar RAG → responder) e aplica guardrails. |
| **Skill dedicada** | Skill invocada pelo agente; encapsula toda a lógica do domínio fiscal: coleta, ingestão e consulta. É o "skill responsável por este trabalho". |
| **Hooks** | Guardrails do opencode executados antes/depois de ações sensíveis (ex.: bloquear acesso a domínios fora da lista permitida, exigir confirmação antes de deletar dados, registrar tentativas de scraping). |
| **Rules** | Regras de comportamento do agente (ex.: "nunca inventar informação", "toda resposta deve citar fonte", "espaçar requisições aos sites"). |
| **Coletor/Scraper** | Acessa os portais oficiais, identifica novos documentos ainda não ingeridos e baixa PDFs/HTML. Respeita intervalos entre requisições. |
| **Parser/Extrator** | Converte PDFs e HTML em texto limpo, pronto para chunking. |
| **Indexador RAG** | Realiza chunking, gera embeddings e persiste na base vetorial em SQLite. Registra metadados do documento (origem, URL, data, status de ingestão). |
| **Camada de Consulta** | Recebe a pergunta do usuário, busca os chunks mais relevantes no RAG e monta o contexto para o LLM responder. |
| **Storage SQLite** | Persistência local única: base relacional (metadados, controle de ingestão, histórico) + extensão vetorial (chunks/embeddings). |

## Stack

- **Plataforma de agente**: opencode (executado localmente).
- **Modelo LLM**: MiniMax-M3 (pago, fornecido pela plataforma opencode).
- **Base RAG**: SQLite com extensão de busca vetorial (ex.: `sqlite-vss` ou `sqlite-vec` — **decisão em aberto** sobre a extensão exata).
- **Execução**: 100% local, na máquina do usuário.
- **Linguagem/scripting**: a definir conforme implementação da skill (provavelmente Python, por afinidade com ecossistema de PDF/scraping — **decisão em aberto**).
- **PDF/HTML parsing**: a definir na implementação (ex.: `pypdf`, `pdfplumber`, `BeautifulSoup`) — **decisão em aberto**.

> **Sprint 14+**: o agente `dfe-agent` e' tambem distribuido como pacote npm `@dfe-agent/dfe-agent` para outros projetos opencode consumirem a base RAG sem clonar o DFe-Agent inteiro. Detalhes em `PLAN_SPRINT14.md` (Apendices A-C) e `AGENTS.md > Distribuicao como pacote npm`. Pipeline Python continua canonico para o proprio DFe-Agent; consumidores npm recebem base pre-buildada via GitHub Releases.

## Constraints técnicas

- **Anti-bot dos portais**: os sites da Fazenda possuem estratégia anti-bot conhecida. A abordagem definida é **espaçar requisições** (sem "metralhar"), sem uso de proxy rotativo, CAPTCHA solving ou similar. Se o agente for bloqueado, ele deve recuar e tentar mais tarde.
- **Volume arbitrário**: a quantidade de PDFs por período é definida unilateralmente pela Fazenda; o sistema deve absorver crescimentos sem mudança de arquitetura.
- **Sem requisito offline**: a coleta depende de conexão à internet; respostas podem usar a base local já populada.
- **Sem restrições de privacidade**: não há dados sensíveis nem requisitos de sigilo.
- **Modelo pago**: MiniMax-M3 é uma API paga; o custo é aceito.
- **Fontes oficiais exclusivamente**: apenas os domínios listados em "Módulos" podem ser acessados pelo coletor (reforçado por hook de guardrail).

### Sites oficiais a monitorar

| Documento/Módulo | URL base |
|---|---|
| NF-e | http://www.nfe.fazenda.gov.br/portal/principal.aspx |
| NFC-e | http://www.nfce.fazenda.gov.br/ |
| CT-e | http://www.cte.fazenda.gov.br/portal/principal.aspx |
| MDF-e | http://www.mdfe.fazenda.gov.br/portal/principal.aspx |
| SPED | http://sped.rfb.gov.br/ |

### Frequência de varredura

A varredura é executada **a cada invocação do agente**, antes de responder. O agente deve sempre garantir que a base está o mais atualizada possível antes de formular a resposta.

## Critérios de aceitação

1. **Coleta completa**: a coleta é considerada correta quando, ao final de uma varredura, não houver mais documentos/PDFs disponíveis nos sites oficiais que não estejam marcados como ingeridos na base.
2. **RAG bem indexado**: a indexação é considerada adequada quando as respostas forem rápidas e assertivas (sem definição numérica de SLA — aferido empiricamente pelo usuário).
3. **Resposta fundamentada**: uma resposta é considerada boa o suficiente quando puder ser corroborada por uma nota técnica, preferencialmente a mais atual disponível para o tema perguntado.
4. **Guardrail de veracidade**: o agente nunca pode inventar informações. Tudo o que ele afirmar deve ser fundamentado em um documento baixado e armazenado na base RAG. Caso não encontre base, deve declarar explicitamente a ausência de informação.

## Decisões em aberto

- Extensão vetorial exata para o SQLite (`sqlite-vss` vs. `sqlite-vec` vs. abordagem própria).
- Linguagem/ferramentas concretas para implementar a skill (provavelmente Python, a confirmar).
- Estratégia concreta de espaçamento entre requisições (intervalo fixo, aleatório com jitter, adaptativo) — apenas o princípio "espaçar" foi definido.
- Política de retenção/atualização: quando uma nota técnica é substituída por uma nova versão, manter a antiga indexada, substituí-la ou versionar.
- Esquema de metadados do documento (campos obrigatórios no SQLite: URL, hash do arquivo, data de publicação, data de ingestão, status).
