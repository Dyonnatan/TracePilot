# Arquitetura do agente local — TracePilot

> O TracePilot passa a ser **dois sistemas**: um agente leve instalado na
> máquina monitorada (recursos, logs, arquivos, atividade de usuário) e o
> servidor TracePilot (processamento pesado: os agentes de IA que já
> existem). Este documento mapeia o que já existe em open source pra cada
> frente de monitoramento, o que vale construir do zero em Rust, e como
> isso se conecta ao pipeline que já temos (OTel Collector → OpenObserve).
>
> Este é o **coletor instalável** — o "TracePilot que se instala". Ele é um
> dos dois caminhos de ingestão: quando a infra não permite instalar nada
> (PaaS, serverless, política de segurança do cliente), a aplicação manda
> telemetria direto pela [API de ingestão](../ingest/), com um
> [guia pronto para IA](ai-integration-guide.md) implementar o envio. Os
> dois caminhos são complementares e terminam no mesmo pipeline — ver
> [ingestion-modes.md](ingestion-modes.md).

## Por que não construir tudo do zero

Cada uma das frentes pedidas — recursos do sistema, logs, integridade de
arquivos (FIM), login de usuário, execução de comando no terminal — tem um
nível de dificuldade/risco bem diferente:

- **Recursos do sistema (CPU, memória, disco)**: trivial e seguro de
  construir do zero. Não envolve dado sensível, não precisa de privilégio
  elevado na maioria dos casos.
- **Logs de aplicação e sistema**: já resolvido — é literalmente o que o
  `otel-collector` que já rodamos faz (receivers `filelog`/`journald`).
- **Integridade de arquivos, login, execução de comando**: aqui mora a
  complexidade real. Fazer isso direito e com segurança exige hooks no
  nível do SO — `inotify`/`fanotify` + auditd no Linux, ETW no Windows,
  EndpointSecurity no macOS — e cada um tem comportamento, permissões e
  armadilhas de segurança próprias. Essa é literalmente a categoria de
  produto "EDR" (Endpoint Detection and Response)/HIDS — reinventar isso
  do zero é caro e arriscado (um bug aqui pode virar um buraco de
  segurança na máquina do cliente, não só um bug funcional).

Por isso a recomendação é um **híbrido**: reaproveitar um projeto open
source maduro pra parte difícil/sensível, e escrever em Rust só a parte
que é genuinamente simples e de baixo impacto.

## Mapeamento por frente de monitoramento

| Frente pedida | Melhor opção | Por quê |
|---|---|---|
| Recursos (CPU, memória, disco, rede) | **Rust próprio** — crate [`sysinfo`](https://docs.rs/sysinfo) | Multiplataforma (Windows/Mac/Linux), não precisa privilégio elevado, binário pequeno, fácil de testar. |
| Logs de aplicação e do sistema | **Já temos** — `otel-collector` (receivers `filelog`, `journald`, e equivalente de Windows Event Log) | Zero código novo — é extensão do pipeline já em produção no projeto. |
| Identificação de arquivos e modificações (FIM) | **Rust próprio (básico)** via crate [`notify`](https://docs.rs/notify) **+ Wazuh (FIM completo)** | `notify` cobre "avisar quando um arquivo monitorado muda" de forma leve e multiplataforma (usa inotify/FSEvents/ReadDirectoryChangesW nativamente). Para FIM de verdade (hash de conteúdo, baseline, detectar quem mudou) o Wazuh já resolve isso pronto. |
| Login de usuário | **Wazuh** (lê Security Event Log no Windows, auditd/logs de autenticação no Linux, logs unificados no macOS) | Cada SO expõe isso de um jeito diferente e sensível a permissão — não vale reimplementar. |
| Execução de comando no terminal | **Wazuh** (módulo de auditoria de comandos) — alternativa mais pesada: eBPF (Falco/Tracee, só Linux) ou ETW (só Windows) | Monitorar execução de processo/comando no nível certo exige hooks de kernel/SO específicos por plataforma. Wazuh já integra isso nos três SOs num agente só. |

## A opção "tudo pronto": Wazuh

[Wazuh](https://wazuh.com) é uma plataforma de segurança open source (fork
ativo do OSSEC) que já cobre quase toda a lista pedida num único agente,
com instaladores prontos pra Windows, macOS e Linux:

- **FIM** — alerta de mudança em arquivo (conteúdo, permissão, dono).
- **Auditoria de sistema** — monitora comportamento de usuário, execução
  de comando, acesso a arquivo crítico.
- **Coleta de log** — de aplicação e do sistema operacional.

Em 2026, comparações (ver fontes) descrevem o Wazuh como a opção mais
completa "pronta pra usar" entre as alternativas abertas, com mais
assembly necessário no osquery (que é mais um framework de consulta
SQL sob demanda do que um agente de streaming contínuo de eventos) e no
Velociraptor (mais focado em forense sob demanda que em monitoramento
contínuo).

**Alternativa mais leve**: [osquery](https://osquery.io) expõe dados do SO
(processos, conexões, pacotes instalados, contas de usuário) via SQL, com
footprint menor — mas pra virar um *stream* contínuo de eventos (não só
consulta pontual) precisa de mais configuração em cima (ex.: `file_events`
table + um backend de auditoria do SO configurado).

## Rust: o que já existe no ecossistema (referência, não adoção direta)

Vale citar — a comunidade Rust já está construindo nessa direção,
confirma que a escolha de linguagem faz sentido pro que foi pedido:

- **[Rustinel](https://www.helpnetsecurity.com/2026/05/11/rustinel-open-source-endpoint-detection-windows-linux/)** — agente em Rust que unifica detecção Windows (ETW) e Linux (eBPF) num único modelo de evento.
- **SecureExec** — agente multiplataforma Linux (eBPF)/macOS (EndpointSecurity)/Windows (ETW), eventos via gRPC.
- **Sentinelle EDR** — EDR self-hosted em Rust pros três SOs, com regras Sigma e MITRE ATT&CK.
- **[Vector](https://vector.dev)** (Datadog) — não é um EDR, mas é a referência de "pipeline de telemetria em Rust, rápido e leve" — prova que dá pra ter algo mais enxuto que o `otel-collector` (que é em Go) pra coleta na ponta, se um dia isso virar gargalo.

Esses projetos são jovens/de nicho — não são recomendados como dependência
de produção ainda (ao contrário do Wazuh, que tem anos de uso e uma
comunidade grande), mas são uma boa referência de arquitetura caso, no
futuro, o time decida migrar a camada de FIM/auditoria pra um agente Rust
próprio em vez do Wazuh.

## Arquitetura proposta

```
Máquina monitorada
├── Wazuh agent (open source, instalador oficial)
│     → FIM, login, execução de comando, logs do SO
│     → grava alertas localmente em JSON (ossec.log / alerts.json)
│
└── local-agent (Rust, construído por nós)
      → sysinfo: CPU, memória, disco, rede — a cada N segundos
      → exporta via OTLP direto pro otel-collector (mesmo protocolo que o demo_app já usa)

           ambos alimentam o pipeline que já existe:

otel-collector (já rodando)
  ├── filelog receiver → tail no JSON de alertas do Wazuh
  └── otlp receiver     → métricas do local-agent (Rust)
        ↓
   OpenObserve (já rodando)
        ↓
   agentes do TracePilot (logs_agent/metrics_agent/traces_agent) — sem
   nenhuma mudança: pra eles, é só mais uma fonte de evidência.
```

Decisão de design: o **único backend novo** é o Wazuh em si — o resto
(coleta de métricas, armazenamento, consulta pelos agentes de IA) reusa
100% do que já está construído. Isso evita duplicar pipeline de
observabilidade.

## Cuidado: implicações de privacidade

Esse agente, por definição, observa login, comandos de terminal e
mudanças de arquivo — é vigilância de endpoint de verdade, não telemetria
de aplicação. Isso é bem diferente (em termos de sensibilidade) de tudo
que o TracePilot fazia até agora. Antes de instalar isso em qualquer
máquina — inclusive a própria, de teste —:

- Precisa ficar claro **o que é coletado e por quanto tempo é guardado**.
- Idealmente a instalação deveria ser **opt-in explícito**, não silenciosa.
- Isso já estava registrado como gap em `architecture.md` ("privacidade"
  como um dos temas que o AKCIT Camp deveria ajudar a amadurecer) — este
  documento é o lugar certo pra aprofundar isso antes de instalar o Wazuh
  em qualquer máquina de verdade, pessoal ou de cliente.

## O que foi construído agora vs. o que fica para depois

**Construído** (ver [`local-agent/`](../local-agent/)): o coletor de
recursos em Rust (`sysinfo` → OTLP), por ser a parte sem implicação de
privacidade/segurança e rápida de validar. E, do outro lado, o caminho que
dispensa instalar qualquer coisa: a [API de ingestão direta](../ingest/),
validada de ponta a ponta — é ela que mantém o TracePilot utilizável em
infra onde este agente não pode rodar.

**Fica como próximo passo deliberado** (não instalado nesta sessão): o
Wazuh agent em si — é uma peça de infraestrutura de segurança real, que
levanta as questões de privacidade acima, e não deveria ser instalado "de
passagem" numa máquina de desenvolvimento sem essa decisão ser tomada com
clareza por quem for usar. Quando for a hora: baixar o instalador oficial
pro SO alvo, apontar a saída de log pro `otel-collector` (via `filelog`
receiver lendo o arquivo de alertas local), sem precisar subir
infraestrutura de indexação própria do Wazuh.

## Fontes

- [Wazuh vs Velociraptor vs Osquery: Self-Hosted EDR & Endpoint Security Guide 2026](https://www.pistack.xyz/posts/2026-05-02-wazuh-vs-velociraptor-vs-osquery-self-hosted-edr-guide-2026/)
- [Compare Wazuh vs. osquery in 2026](https://slashdot.org/software/comparison/Wazuh-vs-osquery/)
- [notify — Rust filesystem library](https://docs.rs/notify/)
- [Vector: Open-Source Observability Data Pipeline](https://vector.dev/)
- [Best Telemetry Agents in 2026: OpenTelemetry, Fluent Bit & More Compared](https://openobserve.ai/blog/best-telemetry-agents/)
- [eBPF Runtime Security Tools 2026: Falco vs Tetragon vs Tracee](https://www.decryptiondigest.com/blog/ebpf-runtime-security-tools-falco-tetragon)
- [Rustinel: Open-source endpoint detection for Windows and Linux](https://www.helpnetsecurity.com/2026/05/11/rustinel-open-source-endpoint-detection-windows-linux/)
