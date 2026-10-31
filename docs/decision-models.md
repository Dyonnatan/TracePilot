# Modelos de decisão ("System 1") — candidatos para o `verifier_agent`

> Categoria de modelo recém-surgida em 2026: em vez de gerar texto livre,
> recebem um **estado** (texto) + uma **pergunta tipada** (sim/não, múltipla
> escolha, nota) e devolvem uma **decisão com probabilidade calibrada**. O
> nome vem de "System 1" (pensamento rápido/automático, em oposição ao
> "System 2" deliberativo dos LLMs generativos tradicionais).
>
> Relevância direta pro TracePilot: o `verifier_agent` hoje pede pro LLM
> escrever `"VEREDITO: SUPORTADO"` em texto livre e a gente faz parsing por
> prefixo de string — funciona, mas é frágil com modelo pequeno. Um modelo
> de decisão responde a pergunta certa ("a hipótese X está sustentada pela
> evidência?") com um sim/não calibrado, sem a fragilidade de parsing de
> texto gerado.

## Os três candidatos

| | Jev | Laya | Kev |
|---|---|---|---|
| Quem | TypeSafe AI | Convai Innovations | jaredpalmer (comunidade) |
| Lançamento | set/2026 (originador da categoria) | set/2026, 3 dias depois do Jev | — |
| Licença | Fechado, só API hospedada | Apache-2.0 | Apache-2.0 |
| Arquitetura | Não divulgada (hospedado) | **Encoder puro** (ModernBERT-large 421M en / mmBERT-base 322M multilíngue) + cabeça de decisão — não é um LLM generativo | LoRA sobre bases Qwen3.5/3.8 (0.8B/4B/9B/27B) |
| Onde roda | Só nuvem (API paga, ~US$0,042/milhão de tokens de entrada) | Local — CPU/GPU, ONNX/GGUF disponíveis | Local — CUDA/ROCm/MLX, serve via `kev.serve` |
| Cabe na GTX 1650 (4GB)? | N/A (não é local) | Sim, folgado (modelo de ~1,3-1,7GB) | Só o **Kev-0.8B** (a doc lista explicitamente "4GB GPU"); Kev-4B já pede GPU de datacenter (L40S/H100) |
| Particularidade | Treinado com RLCD (Reinforcement Learning for Calibrated Decisions) | Por ser um classificador (não gerativo), **não tem como "alucinar" texto** — ele só pontua as opções que você já deu | SDK próprio (`typesafe_sdk`) com tipos `Noul` (sim/não), `Choice` (múltipla escolha), `Score` (nota) |

## Qual faz sentido pro TracePilot

**Laya é o melhor encaixe para o `verifier_agent`**, por três motivos:

1. **Não é gerativo** — é um classificador com cabeça de decisão. Isso
   elimina de vez a classe de erro que motivou o papel do `verifier_agent`
   no primeiro lugar (hipótese "parecendo" sustentada por um texto gerado
   que soa confiante mas não reflete a evidência real).
2. **Minúsculo e rápido** (~1,3-1,7GB, latência citada na casa de
   dezenas de milissegundos) — não compete por VRAM com o modelo principal
   (gemma3:4b ou cyber-analyst-4B) rodando as etapas de resumo/diagnóstico.
   Dá pra rodar os dois ao mesmo tempo na GTX 1650.
3. **Runtime mais simples de integrar**: via `transformers`/ONNX, sem
   precisar subir um segundo servidor HTTP separado (diferente do Kev, que
   exige `uv` + `kev.serve` rodando numa porta própria).

**Kev** é a alternativa caso o encoder do Laya não dê conta de perguntas
mais abertas (ele tem só 421M parâmetros) — Kev-0.8B é maior (base Qwen3.5)
e também cabe nos 4GB, mas tem um custo de integração maior (servidor
próprio via `uv`).

**Jev** fica só documentado para contexto — é a origem da categoria, mas é
API paga e hospedada, incompatível com a decisão de rodar tudo localmente
na GTX 1650.

## Onde isso entraria no código

```
agents/llm/
├── base.py              # LLMProvider — interface já existente (texto livre)
├── cloud_provider.py
├── local_provider.py
└── decision_provider.py # NOVO: interface pra pergunta tipada (sim/não,
                          # múltipla escolha, nota) — Laya como implementação
```

`verifier_agent.py` passaria a ter dois caminhos possíveis: o atual (LLM
generativo + parsing de texto) e um novo baseado em `DecisionProvider`,
perguntando diretamente "a hipótese está sustentada pela evidência?" como
pergunta sim/não. O mesmo padrão serviria, no futuro, para o roteamento
dinâmico do `orchestrator_node` (pergunta de múltipla escolha: "qual
especialista consultar a seguir?") — o TODO que já está registrado em
`code-architecture.md`.

## Status

**Implementado e testado.** `agents/llm/decision_provider.py` usa o Laya,
integrado como checagem independente no `verifier_agent`.

### Benchmark real: Kev-0.8B vs. Laya

O pedido original era testar o Kev com foco em "processar alta quantidade
de dados em praticamente tempo-real". Resultado medido nesta máquina
(GTX 1650, mesma pergunta de verificação nos dois):

| | Kev-0.8B | Laya |
|---|---|---|
| Latência por chamada (aquecido) | ~310-340ms | ~260-330ms |
| Throughput com 10 chamadas simultâneas | ~3,4 req/s (**não paraleliza** — serializa em CPU) | não testado em paralelo, mesma limitação esperada (também CPU) |
| GPU usada? | Não (0 MiB de VRAM durante a chamada) | Não |
| Resposta pro mesmo caso de teste | 0,72 (sustentado) | 0,36 (teste isolado) / 0,74 (com contexto completo da investigação) |

**Por que nenhum dos dois usa GPU aqui**: o mesmo motivo do Laya — o driver
NVIDIA instalado (12.4) é mais antigo do que o PyTorch empacotado por esses
dois projetos espera, então caem pra CPU automaticamente. Isso achata a
vantagem teórica de velocidade de qualquer um dos dois nesta máquina
específica; resolver isso (atualizar o driver) deixou de ser só um "nice to
have" do Laya e virou bloqueio comum aos dois.

**Sobre "tempo real com alto volume"**: nenhum dos dois serve bem um cenário
de *muitos itens por segundo* nesta máquina (~3 req/s é o teto, CPU-bound,
sem paralelismo real no servidor). Mas vale separar dois cenários
diferentes que a frase pode significar:

1. **Uma decisão por investigação** (o que o `verifier_agent` faz hoje) —
   ~300ms é irrelevante perto dos 40-180s que o resto do pipeline (LLM
   generativo) já leva. Não é gargalo.
2. **Classificar um volume alto de itens individuais em tempo real** (ex.:
   triagem contínua de cada log que chega) — isso **não existe ainda** na
   arquitetura do TracePilot (hoje a consulta ao OpenObserve é em lote, só
   quando uma investigação começa). Se for essa a necessidade real, o
   caminho certo não é só escolher entre Kev/Laya — é batelar múltiplas
   perguntas numa única chamada (os dois suportam várias `questions` no
   mesmo `predict`/`systemone`, resolvidas em um único forward pass) em vez
   de uma chamada por item, e/ou resolver o driver de GPU.

### Recomendação

**Manter o Laya como padrão** — desempenho equivalente ao Kev nesta
máquina, mas sem precisar manter um segundo processo de servidor rodando
(`kev.serve` numa porta própria). Kev fica documentado e testado como
alternativa viável, não descartado — se a qualidade da decisão em casos
mais complexos importar mais que a simplicidade operacional, vale
reconsiderar (amostra de 1 caso não é conclusiva o suficiente pra decidir
isso com confiança).

## Fontes

- [Architectural Evolution in Large Language Models: Jamba's Hybrid Transformer-Mamba Design](https://gregrobison.medium.com/architectural-evolution-in-large-language-models-a-deep-dive-into-jambas-hybrid-transformer-mamba-c3efa8ca8cae)
- [Jev, Laya, and the emerging role of decision models](https://runware.ai/blog/jev-laya-and-the-emerging-role-of-decision-models)
- [Laya: Open System One Model as a Jev Alternative](https://innfactory.ai/en/ai-models/laya/)
- [Laya AI: the open decision model that can't hallucinate](https://www.eesel.ai/blog/laya-ai)
- [convaiinnovations/laya · Hugging Face](https://huggingface.co/convaiinnovations/laya)
- [jaredpalmer/kev · GitHub](https://github.com/jaredpalmer/kev)
