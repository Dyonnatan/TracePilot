# Modos de ingestão — coletor instalável e API direta

> Como a telemetria entra no TracePilot. São dois caminhos
> **complementares**, não alternativas concorrentes: o coletor instalável
> é o padrão, a API de ingestão direta cobre o que o coletor não alcança.
> Ambos terminam no mesmo pipeline (otel-collector → OpenObserve →
> agentes de IA), de propósito.

## Os dois caminhos

```
 Caminho 1 — coletor instalável (padrão)
 ┌─────────────────────────────────────┐
 │ máquina/servidor monitorado         │
 │  app ──(log em arquivo/stdout)      │
 │  SO  ──(CPU, memória, disco)        │
 │            │                        │
 │   coletor TracePilot (local-agent/) │
 └────────────┼────────────────────────┘
              │ OTLP
              ▼
 Caminho 2 — API de ingestão direta (complementar)
 ┌─────────────────────────────────────┐
 │ aplicação (qualquer infra)          │
 │  código manda só o que importa ─────┼──► POST /v1/events  (ingest/)
 └─────────────────────────────────────┘      JSON simples
                                                   │ traduz pra OTLP
              ┌────────────────────────────────────┘
              ▼
       otel-collector ──► OpenObserve ──► agentes do TracePilot
```

Decisão central: **a API direta não cria um segundo pipeline**. Ela
traduz o JSON recebido para OTLP e entrega no mesmo collector, com os
mesmos nomes de campo que `agents/tools/openobserve_client.py` já
consulta. Para os agentes de IA, não existe diferença entre evidência que
veio do coletor e evidência que veio da API — só o atributo
`tracepilot.ingest_mode` distingue a origem, se alguém quiser auditar.

## Caminho 1: coletor instalável (`local-agent/`)

O "TracePilot instalável": um binário em Rust (~2MB, sem runtime externo)
instalado na máquina monitorada. Hoje coleta recursos do sistema (CPU,
memória, disco) via `sysinfo` e exporta por OTLP. Detalhes e o que fica
fora de propósito dele (FIM, login, execução de comando → Wazuh) em
[local-agent-architecture.md](local-agent-architecture.md).

**Quando é o caminho certo** (o padrão, sempre que possível):

- Dá acesso a **recursos do SO** — CPU, memória, disco — que a aplicação
  não tem como reportar sobre si mesma. É a evidência que distingue "o
  código tem um bug" de "a máquina estava sem memória".
- **Não exige mudar a aplicação.** Nenhuma linha de código novo, nenhum
  deploy, nenhum risco de a instrumentação quebrar a aplicação.
- Funciona para aplicação **legada ou de terceiros**, cujo código não se
  pode (ou não se quer) tocar.
- Continua reportando quando a aplicação **morreu** — e o estado da
  máquina no minuto da queda costuma ser a evidência decisiva.

> Nota de nomenclatura: "coletor TracePilot" (`local-agent/`) é o agente
> instalado na ponta; "otel-collector" é o componente do pipeline que roda
> junto ao servidor TracePilot (`docker-compose.yml`). São peças
> diferentes — o primeiro manda dado para o segundo.

## Caminho 2: API de ingestão direta (`ingest/`)

A aplicação se conecta ao TracePilot e manda log/span em JSON simples.
Implementação em [`ingest/`](../ingest/), contrato e guia de implementação
em [ai-integration-guide.md](ai-integration-guide.md).

**Quando é o caminho certo:**

- **Infra que não permite instalador**: PaaS gerenciada (Heroku, Render,
  App Runner), função serverless, container gerenciado sem acesso ao host,
  ou política de segurança do cliente que proíbe agente na máquina. Sem
  este caminho, esses cenários simplesmente ficariam de fora do
  TracePilot.
- **Otimizar o envio**: a aplicação sabe o que importa. Em vez de tail-ear
  todo o log da máquina e filtrar depois, ela manda o erro já estruturado
  (exceção + stacktrace + `trace_id` + rota) e amostra o sucesso. Menos
  volume trafegado e armazenado, com evidência de qualidade maior.
- **Contexto que só a aplicação tem**: `order_id`, `quantity`, o passo do
  fluxo de negócio. Isso não aparece em métrica de SO nem em log não
  estruturado.

**O que ele não dá** — e por isso é complementar, não substituto: não vê
recursos do SO, exige mudança no código da aplicação, e para de reportar
exatamente quando a aplicação cai.

## Usar os dois juntos

É a configuração completa, e a recomendada quando há acesso à máquina:
coletor instalado dando a camada de infraestrutura, aplicação mandando a
camada de aplicação. Uma investigação com as duas fontes consegue
responder "a exceção foi de divisão por zero **e** a máquina estava com
94% de memória" — que é o tipo de correlação que o TracePilot existe para
fazer.

Cuidado único: **não duplicar a mesma fonte**. Se o coletor já está
lendo o arquivo de log da aplicação, a aplicação não deve mandar os mesmos
registros pela API — evidência duplicada polui a investigação e infla
custo de armazenamento sem agregar informação.

## Por que um guia para IA, e não só um SDK

O caminho 2 precisa de código dentro da aplicação do cliente — em qualquer
linguagem, em qualquer framework. Manter SDK oficial para cada stack é um
custo de manutenção que um projeto deste tamanho não sustenta, e um SDK
sempre deixa de fora a stack do próximo cliente.

A aposta é outra: publicar o **contrato** (o que o TracePilot precisa
receber e por quê) num formato que uma IA trabalhando no código do cliente
consiga aplicar na stack que já existe ali — ver
[ai-integration-guide.md](ai-integration-guide.md). O guia é servido pela
própria instância em `GET /v1/guide`, então a IA busca a versão que
corresponde ao TracePilot que ela vai alimentar, em vez de uma cópia
colada que envelhece.

O que fecha o ciclo é o **retorno da API**: `POST /v1/events` responde com
`warnings` apontando o que falta no lote para a investigação funcionar
("nenhum log com `trace_id`", "nenhum span com `status=ERROR`",
"nenhum `exception.stacktrace`"). A IA manda um lote de teste, lê os
avisos e corrige — sem ninguém precisar abrir o OpenObserve para conferir
se o campo certo chegou. É o que torna "guia + API" uma alternativa
viável a um SDK por linguagem: a validação é automática e vem da
instância real.

## Segurança

A API de ingestão é **plano de dados exposto** — recebe tráfego da
aplicação do cliente, possivelmente da internet pública. Por isso:

- Roda como **serviço separado** do `webapp/` (plano de controle, painel
  do operador). Um processo só daria ao tráfego do cliente a mesma
  superfície de ataque do painel.
- Autentica por **chave de API por serviço integrado**
  (`TRACEPILOT_INGEST_KEYS`). Sem chave configurada, a API aceita qualquer
  requisição — aceitável em desenvolvimento local, inaceitável em
  produção: qualquer um poderia escrever evidência falsa numa
  investigação. `GET /v1/health` denuncia esse estado no campo `auth`.
- Expõe **só escrita de telemetria**. Não lê investigação, não consulta
  OpenObserve, não fala com os agentes de IA — mesmo raciocínio do
  `OpenObserveClient`, que só expõe métodos de leitura.
- Limita lote a 500 eventos (`TRACEPILOT_INGEST_MAX_EVENTS`).

Pendente para produção, deliberadamente fora do MVP: TLS (hoje a
expectativa é um proxy reverso na frente), *rate limit* por chave, e
amarrar a chave ao `service` que ela pode escrever (hoje qualquer chave
válida pode escrever em nome de qualquer serviço).

## Estado atual

| Peça | Estado |
|---|---|
| Coletor instalável — recursos do SO | Protótipo validado no Linux ([`local-agent/`](../local-agent/)); não empacotado como instalador (MSI/pkg/deb) nem testado em Windows/macOS. |
| Coletor instalável — tail de log | Coberto pelo `otel-collector` (receivers `filelog`/`journald`), ainda não configurado por padrão no `docker-compose.yml`. |
| API de ingestão direta | **Funcional e validada de ponta a ponta**: lote enviado por `POST /v1/events` chega ao OpenObserve com os campos que os agentes consultam (`body`, `severity`, `trace_id`, `exception_*`, `operation_name`, `span_status`, `http_route`, `duration`, `events`), conferido por consulta via `OpenObserveClient`. |
| Guia para IA | Escrito ([ai-integration-guide.md](ai-integration-guide.md)) e servido em `GET /v1/guide`. |
| TLS / rate limit / chave amarrada a serviço | Pendente (ver "Segurança"). |
