# Glossário de conceitos — Agentes de IA

> Síntese própria (não é cópia) dos conceitos e nomenclaturas relevantes do
> material de referência do AKCIT Camp ("Agentes de Inteligência
> Artificial"), reescrita para servir de vocabulário comum ao projetar a
> arquitetura do TracePilot e ao montar o pitch. Cada seção também traz uma
> nota de "aplicação ao TracePilot" ligando o conceito ao que já existe no
> scaffold (ver [architecture.md](architecture.md) e
> [code-architecture.md](code-architecture.md)).
>
> Cobertura atual: **Capítulos 1 e 2** (fundamentos de sistemas de agentes;
> arquiteturas de agentes).

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

## Capítulo 2 — Arquiteturas de agentes

> Enquanto o Capítulo 1 classifica agentes por *capacidade* (os 5 tipos),
> o Capítulo 2 olha para a *estrutura interna*: como o agente é organizado
> para transformar percepção em ação. Três categorias — reflexiva, baseada
> em modelo e híbrida — mais os critérios para escolher entre elas e os
> padrões de projeto recorrentes.

### 2.1 Arquitetura reflexiva

A forma mais simples: decide **só** com a percepção atual, aplicando
regras fixas de condição→ação, sem memória nem modelo do mundo. Rápida,
barata de construir e ideal quando o ambiente é totalmente observável e a
velocidade de resposta importa mais do que sofisticação — mas falha em
ambientes parciais/dinâmicos, porque não "lembra" nada e não planeja.
Exemplos clássicos: termostato, robô aspirador que só reage a colisão,
chatbot que responde sempre a mesma coisa para o mesmo gatilho.

**Aplicação ao TracePilot**: nenhum agente do TracePilot é puramente
reflexivo — mas a falha controlada do `demo_app` (`ZeroDivisionError`
quando `quantity == 0`) é, ela mesma, uma regra reflexiva clássica
(condição fixa → efeito fixo), o que é proposital: serve como "gabarito"
determinístico para os agentes investigarem.

### 2.2 Arquitetura baseada em modelo (estado interno, planejamento simples)

Acrescenta ao agente um **estado interno** que é atualizado a cada
percepção — um "modelo do mundo" que permite lembrar o que já aconteceu e
inferir o que não está diretamente observável agora. Com esse estado, o
agente consegue formas simples de planejamento (simular mentalmente o
efeito de uma ação antes de agir) e evitar repetir trabalho. Custo: mais
complexidade computacional e risco de o modelo interno ficar desatualizado
ou errado. Exemplos: aspirador que constrói um mapa do cômodo, NPC de jogo
que lembra jogadas anteriores, agente conversacional com memória/contexto.

**Aplicação ao TracePilot**: este é o mapeamento mais direto do capítulo —
o `IncidentState` (TypedDict) do `agents/orchestrator.py` **é** esse
estado interno/modelo do mundo: ele acumula `evidence_logs`,
`evidence_metrics`, `evidence_traces` e `hypotheses` conforme cada
especialista roda, exatamente como a arquitetura baseada em modelo
descreve — cada nó do grafo não decide só com sua própria percepção
(a fonte de dados que ele consulta), mas também com o que os nós
anteriores já registraram no estado compartilhado.

### 2.3 Arquitetura híbrida (deliberação + reação)

Combina uma **camada reativa** (respostas rápidas e de baixo nível a
estímulos urgentes), uma **camada deliberativa** (raciocínio de alto
nível, planejamento orientado a objetivos, usa o modelo do mundo) e,
frequentemente, uma **camada de coordenação** que faz a mediação entre as
duas — decide quando a reação tem prioridade e quando seguir o plano.
Permite ao agente não ficar nem "paralisado pensando" nem "agindo de forma
míope". Exemplo citado: um carro autônomo que reage em milissegundos a um
obstáculo (reativo) mas também planeja a rota ótima até o destino
(deliberativo). A arquitetura **BDI** (*Belief-Desire-Intention* — crenças,
desejos, intenções) é apontada como um exemplo consagrado desse estilo
híbrido/deliberativo.

**Aplicação ao TracePilot**: dá vocabulário preciso para descrever o
`orchestrator_node` como camada de coordenação (hoje simples, mas o TODO
já registrado em `code-architecture.md` é justamente fazê-lo decidir
dinamicamente — um papel de coordenação de verdade) mediando entre os
especialistas (mais próximos de execução/reação a uma consulta pontual) e
o par diagnóstico+verificador (a camada deliberativa, que raciocina sobre
o estado acumulado para formar e checar hipóteses).

### 2.4 Como escolher a arquitetura para cada problema

Quatro critérios guiam a escolha, sem resposta única:

1. **Complexidade/dinamismo do ambiente** — ambiente simples e estático →
   reflexivo basta; ambiente complexo/dinâmico → precisa de estado
   interno (modelo) ou mais.
2. **Disponibilidade de dados/conhecimento do domínio** — muito dado e
   domínio bem modelado favorece arquiteturas baseadas em modelo; baixa
   observabilidade praticamente exige estado interno, senão o agente fica
   "cego" para o que não está na percepção do instante.
3. **Requisitos de latência** — tempo real/quase real favorece reativo (ou
   a camada reativa de um híbrido); se um atraso de segundos for
   aceitável, arquiteturas deliberativas são viáveis. É literalmente
   uma decisão de SLO/SLA.
4. **Custo de desenvolvimento e computação** — reflexivo é mais barato de
   construir e rodar; modelo/planejamento/aprendizado custam mais
   (memória, busca, chamadas a LLM, bases vetoriais). Regra prática: um
   MVP costuma começar reativo e evoluir para memória/planejamento por
   iteração, só quando necessário.

**Aplicação ao TracePilot**: usando a própria classificação de ambiente do
Capítulo 1 (já aplicada no glossário acima — investigação de incidente é
parcialmente observável, estocástica, sequencial, dinâmica e
multiagente), os quatro critérios deste capítulo convergem para a mesma
conclusão: **não cabe arquitetura reflexiva** (ambiente complexo/parcial
demais) nem exige velocidade de milissegundos (diagnóstico tolera
segundos/minutos de deliberação, ao contrário de um carro autônomo) — ou
seja, o critério de latência *permite* ir além do reativo, e o critério de
complexidade *exige* isso. Esse é um argumento direto e citável no pitch
para justificar a escolha por uma arquitetura baseada em modelo +
deliberação (via LangGraph), em vez de um agente reativo simples ou um
único prompt.

### 2.5 Padrões de projeto para agentes

Três padrões recorrentes para organizar agentes e sistemas multiagentes —
não são mutuamente exclusivos, sistemas complexos costumam combinar os
três:

- **Planejador-Executor**: separa quem planeja (recebe um objetivo,
  produz um plano/sequência de subtarefas) de quem executa (realiza cada
  passo do plano, possivelmente chamando ferramentas). Ganha-se controle
  e verificação de qualidade — o plano pode ser checado antes de rodar, e
  a execução pode ter salvaguardas por passo.
- **Supervisor-Trabalhador**: um agente supervisor decompõe o problema em
  subtarefas, delega a agentes trabalhadores especializados, monitora o
  progresso e agrega os resultados. Espelha uma hierarquia
  gerente/equipe: dá paralelismo (trabalhadores em paralelo) e controle
  central (o supervisor aplica políticas e checa qualidade). O próprio
  material usa, como exemplo ilustrativo, um sistema multiagente de
  análise financeira com um supervisor delegando a trabalhadores
  especializados (coleta de dados, cálculo de indicadores, visualização)
  — estrutura quase idêntica ao desenho do TracePilot.
- **Agente com Ferramentas/Skills**: em vez de embutir todo conhecimento
  no agente central, ele aciona ferramentas/serviços externos (busca,
  calculadora, banco de dados, API) para subtarefas fora de sua
  competência nativa — o padrão por trás do "tool calling" em frameworks
  como LangChain. Ganha-se modularidade: novas skills se desenvolvem e se
  plugam independentemente.

**Aplicação ao TracePilot**: os três padrões já aparecem simultaneamente
no scaffold atual, o que vale a pena nomear explicitamente no pitch:

| Padrão | Onde está no TracePilot |
|---|---|
| Supervisor-Trabalhador | `orchestrator.py` (supervisor) + `logs_agent`/`metrics_agent`/`traces_agent` (trabalhadores especializados) |
| Planejador-Executor | Hoje o "plano" é fixo (fluxo linear no grafo); o TODO de roteamento dinâmico no `orchestrator_node` é exatamente evoluir para um planejador de verdade, que decide a sequência de subtarefas por incidente, separado da execução de cada especialista |
| Ferramentas/Skills | `agents/tools/openobserve_client.py` é a "ferramenta" que os especialistas acionam para consultar logs/métricas/traces — mesmo padrão de tool-calling do LangChain/LangGraph |

Isso dá uma resposta direta e bem fundamentada para "por que essa
arquitetura e não outra mais simples": o TracePilot não inventa um
desenho novo — combina três padrões já consolidados na literatura de
agentes, cada um resolvendo um problema específico de organização
(delegação, planejamento, acesso a dados externos).

---

## Fontes

Síntese própria a partir de: ebook "Agentes de Inteligência Artificial"
(AKCIT/UFG), capítulos 1 e 2; e do cheatsheet "Agentes de Inteligência
Artificial" do mesmo programa. Nenhum trecho é cópia literal do material
original — definições e exemplos foram reescritos e reorganizados em
função da arquitetura do TracePilot.
