# Arquitetura geral — TracePilot

> Este documento reúne, de forma estruturada, o conteúdo completo da
> proposta submetida ao AKCIT Camp. Serve como fonte única de verdade para
> montar o pitch (slides, formulário, demo) — nada do texto original deve
> se perder ao copiar daqui.

## 1. Problema e oportunidade

Quando uma aplicação apresenta erros em produção, identificar a causa pode
levar mais tempo do que detectar a falha. Equipes de desenvolvimento
precisam correlacionar manualmente logs, métricas, traces, alterações de
código e relatos de usuários. Muitas vezes, uma reclamação como "não
consegui concluir a operação" chega sem contexto suficiente para
reproduzir o problema. A investigação consome tempo técnico e pode
prolongar indisponibilidades, especialmente em equipes sem profissionais
dedicados à confiabilidade de sistemas (SRE).

## 2. Solução proposta

O TracePilot propõe uma camada inteligente de investigação integrada a
ferramentas abertas de observabilidade. Quando ocorre um erro, o sistema
correlaciona, quando disponíveis e autorizados, eventos da jornada do
usuário (RUM e sessão), requisições, logs, métricas, traces e histórico de
mudanças. Agentes especializados investigam essas fontes, formulam e
confrontam hipóteses, solicitam evidências adicionais e produzem um
diagnóstico rastreável. O resultado é um relatório técnico com contexto,
causa provável, evidências, limitações, passos sugeridos de reprodução e
possíveis correções, com opção de gerar uma issue em ferramentas de
desenvolvimento.

### Fluxo (visão técnica)

```
App instrumentada (demo_app)
        │  OpenTelemetry (traces/logs/métricas)
        ▼
  OTel Collector  ──────▶  OpenObserve (armazenamento/consulta)
        │
        ▼
  Orquestrador (LangGraph) ─┬─▶ logs_agent
                            ├─▶ metrics_agent
                            ├─▶ traces_agent
                            ▼
                     diagnosis_agent ──▶ verifier_agent ──▶ relatório
```

## 3. Por que agentes de IA

Incidentes não seguem um roteiro único: o resultado de uma consulta pode
mudar a hipótese e exigir novas verificações em outra ferramenta. Um agente
**orquestrador** coordena as etapas; **especialistas** em logs, métricas e
traces coletam e analisam sinais; um agente de **diagnóstico** consolida
hipóteses; e um **verificador** questiona conclusões sem suporte
suficiente.

Esse desenho é uma instância do padrão de projeto **Supervisor-Trabalhador**
(um dos blueprints citados no material de referência do AKCIT Camp para
estruturar sistemas de agentes de forma eficaz e manutenível). A escolha de
**LangGraph** como framework de orquestração também segue a recomendação do
mesmo material: ele é indicado "quando o agente ou aplicação de LLM exige
lógica complexa de controle, múltiplos agentes interagindo e flexibilidade
máxima nas transições" — exatamente o caso de uma investigação de incidente,
que não é linear.

A arquitetura multiagente será comparada experimentalmente com alternativas
mais simples (LLM único, agente único com ferramentas), para comprovar
quando a colaboração realmente compensa sua complexidade (ver
`benchmark/README.md`).

## 4. Diferenciais e implementação

A proposta concentra-se na passagem do erro percebido pelo usuário para um
caso técnico investigado e acionável, evitando reconstruir plataformas
completas de observabilidade. São usados:

- **OpenTelemetry** + **OpenObserve** como base de telemetria.
- **Python** e **LangGraph** para a orquestração da investigação.
- Modelos **open-weight e processamento local** (via Ollama), quando
  adequado, para maior controle dos dados — combinados com um provider
  cloud, atrás de uma interface comum (`agents/llm/`), para flexibilidade
  entre custo/latência e privacidade.
- Uma aplicação de teste (`demo_app/`) com falhas controladas e
  instrumentação ponta a ponta.

## 5. Gaps de hoje e plano de validação

Desafios identificados:

- Obter diagnósticos consistentes e evitar alucinações — o verifier_agent
  existe justamente para confrontar hipóteses com evidência real.
- Correlacionar dados heterogêneos (logs, métricas, traces, jornada do
  usuário) de forma confiável.
- Gerenciar custo e latência de inferência entre múltiplos agentes.
- Limitar o acesso dos agentes a operações seguras (hoje, `OpenObserveClient`
  só expõe métodos de consulta/leitura — ver `docs/code-architecture.md`).

Plano de validação:

- Usar o benchmark aberto **OpenRCA** para avaliar identificação de
  causa-raiz, comparando LLM simples, agente único e multiagente (ver
  `benchmark/README.md`).
- Laboratório próprio para verificar a correlação entre a ação do usuário,
  a falha de backend e o relatório gerado.
- Medir acurácia, tempo, custo e fundamentação das evidências — resultados
  ainda não medidos.

### Gaps específicos de LLMOps (ainda não cobertos neste scaffold)

O material de referência do AKCIT Camp lista um conjunto de práticas de
LLMOps que ainda não estão implementadas e ficam como próximos passos:

- **Rastreabilidade**: versão do modelo, prompts e saídas logados por
  investigação (hoje os providers de LLM não logam nada ainda — TODO em
  `agents/llm/cloud_provider.py` e `local_provider.py`).
- **Memória**: nenhuma memória de incidentes passados existe ainda. O
  roadmap prevê memória semântica (vector store — ex. ChromaDB/Qdrant) para
  correlacionar um incidente novo com casos já investigados.
- **Padrão de deploy**: o MVP atual assume invocação síncrona (API REST,
  uma investigação por request). Evoluir para um padrão assíncrono (fila de
  mensagens, ex. RabbitMQ) é necessário para investigações mais longas ou
  paralelizar coleta de evidências sem travar o request principal.
- **Observabilidade dos próprios agentes**: monitorar os agentes (latência,
  custo por chamada, taxa de erro) é tão necessário quanto monitorar a
  aplicação investigada.
- **Segurança de segredos**: `.env.example` já define onde ficam as chaves,
  mas nenhuma rotação ou Secrets Manager está em uso — aceitável para
  protótipo, não para produção.

## 6. Contribuição do AKCIT Camp

O programa permitirá aprofundar e aplicar prompting, RAG, function calling,
orquestração e autonomia multiagente, avaliação, guardrails, memória,
privacidade e LLMOps em um protótipo funcional. As mentorias ajudarão a
validar o problema junto a equipes de desenvolvimento, definir o MVP e
explorar a viabilidade de um produto acessível para software houses,
startups e pequenas equipes de TI.
