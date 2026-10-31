# Glossário de conceitos — Agentes de IA

> Síntese própria (não é cópia) dos conceitos e nomenclaturas relevantes do
> material de referência do AKCIT Camp ("Agentes de Inteligência
> Artificial"), reescrita para servir de vocabulário comum ao projetar a
> arquitetura do TracePilot e ao montar o pitch. Cada seção também traz uma
> nota de "aplicação ao TracePilot" ligando o conceito ao que já existe no
> scaffold (ver [architecture.md](architecture.md) e
> [code-architecture.md](code-architecture.md)).
>
> Cobertura atual: **Capítulo 1** (fundamentos de sistemas de agentes).
> Capítulo 2 (arquiteturas de agentes) entra numa próxima atualização deste
> documento.

## Capítulo 1 — Fundamentos de sistemas de agentes

### O que é um agente inteligente

Um agente é uma entidade que percebe o ambiente ao seu redor (via
"sensores", em sentido amplo) e age sobre ele (via "atuadores") de forma
autônoma, perseguindo um objetivo — sem precisar de um humano guiando cada
passo. Ele opera num ciclo contínuo: **percebe → decide → age**, e esse
ciclo se repete indefinidamente.

**Aplicação ao TracePilot**: cada agente especialista (logs/métricas/
traces) é essa unidade perceber→decidir→agir em miniatura — percebe os
dados de uma fonte de telemetria, decide o que é relevante, age devolvendo
evidências ao estado compartilhado.

### Propriedades que definem um agente "de verdade"

| Propriedade | Significado |
|---|---|
| Autonomia | Opera sem supervisão passo a passo. |
| Reatividade | Responde a mudanças relevantes no ambiente em tempo hábil. |
| Proatividade | Toma iniciativa — planeja à frente, não só reage. |
| Adaptabilidade / aprendizagem | Melhora com a experiência ao longo do tempo. |
| Habilidade social | Coopera/negocia/comunica com outros agentes ou humanos. |

**Aplicação ao TracePilot**: o orquestrador precisa de proatividade (decidir
qual especialista consultar a seguir) e habilidade social (coordenar vários
agentes); a adaptabilidade é hoje um gap — fica como roadmap de memória
vetorial de incidentes passados (já registrado em `architecture.md`).

### Racionalidade não é infalibilidade

Um agente racional escolhe a melhor ação **dado o que ele sabe no
momento** — isso não garante acerto se o ambiente for imprevisível ou a
percepção for incompleta. Um agente pode agir corretamente e ainda assim
chegar a um resultado ruim, sem que isso signifique que ele "errou" do
ponto de vista de decisão.

**Aplicação ao TracePilot**: é exatamente por isso que o relatório final
deve expor **limitações e nível de confiança**, não só uma causa-raiz
"definitiva" — o `verifier_agent` existe para não deixar uma hipótese
plausível, mas mal sustentada, virar conclusão.

### Dimensões para classificar o ambiente de um agente

Essas dimensões não são mutuamente excludentes — um ambiente real se
encaixa em várias ao mesmo tempo:

- **Observabilidade**: total (toda informação relevante está na percepção
  atual, não precisa de memória) vs. parcial (há informação oculta, exige
  manter estado interno).
- **Determinismo**: determinístico (mesmo estado + mesma ação = mesmo
  resultado, sempre) vs. estocástico (resultado tem incerteza). Existe
  ainda o caso de ambiente **estratégico**: determinístico, mas o
  resultado depende também das ações de outros agentes (ex.: um
  adversário em um jogo).
- **Episodicidade**: episódico (cada decisão é isolada, sem relação com a
  anterior) vs. sequencial (decisões de agora afetam o futuro).
- **Dinamicidade**: estático (nada muda enquanto o agente delibera) vs.
  dinâmico (o mundo continua mudando durante a decisão) vs. semidinâmico
  (o ambiente não muda sozinho, mas o desempenho do agente piora se ele
  demorar para agir).
- **Continuidade**: discreto (percepções/ações em um conjunto finito) vs.
  contínuo (variam em um espectro, potencialmente infinito).
- **Número de agentes**: único vs. multiagente.

**Aplicação ao TracePilot**: o ambiente de uma investigação de incidente é
**parcialmente observável** (nem toda telemetria está disponível/
autorizada), **estocástico** (a causa-raiz nem sempre segue um padrão
fixo), **sequencial** (o resultado de uma consulta muda a próxima
hipótese — por isso LangGraph, e não um pipeline linear fixo), **dinâmico**
(o sistema investigado continua operando e gerando novos dados durante a
investigação) e **multiagente** por definição. Essa classificação, em si,
já é uma boa justificativa técnica para o pitch de por que a arquitetura
não poderia ser mais simples (um único prompt não dá conta de um ambiente
com essas cinco características simultâneas).

### Os cinco tipos de agente (do mais simples ao mais sofisticado)

Cada nível acumula as capacidades do anterior:

1. **Reflexo simples**: decide só com a percepção atual, via regras fixas
   de condição→ação. Sem memória, sem planejamento. Funciona bem em
   ambientes totalmente observáveis e estáticos; falha em ambientes
   parciais/dinâmicos.
2. **Reflexo baseado em modelo**: mantém um estado interno (um "modelo do
   mundo") que é atualizado a cada percepção, permitindo lidar com
   ambientes parcialmente observáveis — mas ainda decide por regras
   reativas, só que informadas pelo modelo.
3. **Baseado em objetivos**: além do modelo, tem uma meta explícita e
   **planeja** sequências de ação para alcançá-la, em vez de só reagir.
4. **Baseado em utilidade**: quando há vários caminhos possíveis até o
   objetivo, usa uma função de utilidade para escolher o melhor entre
   eles (não só "atinge a meta", mas "atinge do jeito mais desejável").
5. **De aprendizagem**: incorpora tudo acima e aprende com a experiência,
   via quatro componentes conceituais — um **elemento de desempenho**
   (escolhe as ações, como nos tipos anteriores), um **elemento crítico**
   (avalia se o resultado foi bom), um **elemento de aprendizado** (ajusta
   o agente com base nessa avaliação) e um **gerador de problemas**
   (propõe novas situações para o agente explorar e melhorar).

**Aplicação ao TracePilot**: hoje os agentes (`diagnosis_agent`,
`verifier_agent`) são essencialmente **baseados em objetivos** (a meta é
"diagnóstico correto e sustentado por evidência"). O `verifier_agent` já
tem um papel parecido com o de **elemento crítico** do tipo 5 — avalia se
a conclusão do `diagnosis_agent` está bem sustentada. O que falta para
chegar a um agente de tipo 5 completo é o **elemento de aprendizado**
propriamente dito: hoje nada no sistema aprende com investigações
passadas — é exatamente o gap de "memória vetorial de incidentes" já
registrado como roadmap.

### Sistemas multiagentes (MAS)

Um MAS é um ambiente onde várias entidades autônomas coexistem — cooperando,
competindo ou só dividindo o mesmo espaço. Trazem robustez e paralelismo,
mas também risco de comportamento emergente indesejado (ex.: agentes
competitivos entrando em ciclo destrutivo, ou agentes cooperativos travados
esperando uns pelos outros). O material cita, como peças de infraestrutura
para levar times de agentes à produção, ferramentas de mensageria (ex.
RabbitMQ) para coordenação assíncrona e armazenamento de estado
compartilhado (ex. Redis) — mesmas ferramentas já registradas como roadmap
de LLMOps em `architecture.md`.

**Aplicação ao TracePilot**: confirma, com uma fonte adicional, a decisão
já tomada de registrar RabbitMQ/Redis como evolução futura (não escopo do
scaffold atual) para quando o volume de investigações justificar
assincronia.

### Aplicações citadas (contexto, não detalhado aqui)

O capítulo encerra listando aplicações já comuns de agentes (chatbots de
atendimento, automação industrial, assistentes pessoais) e aponta a
tendência de usar LLMs como "motor de raciocínio" dos agentes — exatamente
o caminho que frameworks como LangChain/LangGraph/CrewAI seguem, e que o
TracePilot já adota.

---

## Próxima atualização deste documento

Cole aqui (ou me envie) o conteúdo do **Capítulo 2 — Arquiteturas de
Agentes** (reflexiva, baseada em modelo, híbrida, critérios de escolha e
padrões de projeto) para eu completar este glossário com a mesma
abordagem — síntese própria + aplicação direta ao TracePilot.
