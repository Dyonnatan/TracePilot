# Ambiente de referência monitorado — kickoff

> Documento de início para quem for tocar esta frente do projeto. Define o
> objetivo, o escopo, o que já existe para se apoiar, e as decisões que
> ficam a cargo de quem pegar a tarefa. Não é uma especificação fechada —
> é o ponto de partida.

## Contexto

O `demo_app/` atual (ver [code-architecture.md](code-architecture.md)) é
um único serviço FastAPI com uma falha controlada simples
(`ZeroDivisionError` em `/checkout`). Ele serve bem para validar a fiação
básica (OTel → Collector → OpenObserve → agentes), mas é simples demais
para representar os cenários reais que o TracePilot quer atacar: um
incidente de produção normalmente envolve **múltiplos componentes**
(serviços, banco de dados, rede, recursos de host) e a causa raiz pode
estar em qualquer um deles, não só no código de um endpoint.

Esta frente é sobre construir um **ambiente de referência** mais completo —
via Docker — que simule um ecossistema monitorado de verdade, para que os
agentes do TracePilot tenham cenários realistas (e variados) de incidente
para investigar.

## Duas frentes distintas (não confundir)

1. **Ambiente de referência monitorado (Docker)** — foco principal deste
   documento. Construir a infraestrutura simulada (app + rede + banco +
   logs + métricas de CPU/RAM) e o catálogo de falhas injetáveis.
2. **Amostra do dataset de teste (OpenRCA)** — frente paralela e
   independente, só para começar a medir a capacidade do modelo (LLM puro,
   sem os agentes ainda) em identificar causa-raiz. Não depende do
   ambiente Docker estar pronto — pode rodar em paralelo, hoje mesmo, só
   selecionando um recorte pequeno (5-10 casos) do OpenRCA representando
   tipos diferentes de causa raiz. Ver `benchmark/README.md` para o plano
   de avaliação completo; aqui só a amostra pequena para um teste rápido
   de capacidade.

Este documento foca na frente 1. A frente 2 é mencionada só para deixar
registrado que são esforços separados e podem ser paralelizados por
pessoas diferentes.

## Objetivo do ambiente de referência

Um ecossistema, orquestrado via Docker (compose, possivelmente em
`reference-env/` na raiz do repo, separado do `docker-compose.yml`
principal de telemetria), que:

- Tenha **múltiplos componentes** (pelo menos: uma aplicação com 2+
  serviços, um banco de dados, e algo representando tráfego de rede entre
  eles).
- Exponha **sinais de observabilidade completos**: logs, métricas de
  aplicação, métricas de host (CPU, RAM, disco, rede), e traces —
  integrados ao mesmo pipeline que o TracePilot já consome (OTel Collector
  → OpenObserve, configurados na raiz do repo).
- Permita **injetar falhas de forma controlada e repetível** (não
  aleatória), cobrindo categorias diferentes de causa raiz — não só bugs
  de código.

## O que já existe para se apoiar

- `docker-compose.yml` + `otel-collector-config.yaml` na raiz: já sobe
  OpenObserve + OTel Collector. O ambiente de referência deve **exportar
  para o mesmo Collector** (mesma rede Docker, mesmo endpoint OTLP) em vez
  de duplicar a stack de telemetria.
- `demo_app/main.py`: exemplo mínimo de como instrumentar um serviço
  Python com OpenTelemetry e expor uma falha determinística — útil como
  referência de padrão, não como base a ser estendida (o ambiente novo
  provavelmente vai além de Python/FastAPI).
- `docs/architecture.md`: contexto de por que a correlação entre múltiplas
  fontes de sinal é o cerne da proposta — o ambiente de referência existe
  para dar material real a essa correlação.

## Decisões em aberto (a cargo de quem pegar esta frente)

Estas são decisões de projeto, não técnicas — ficam para quem tocar a
frente definir, com base no que for mais fácil de demonstrar no pitch/demo:

- **Construir do zero vs. adotar um projeto open source já instrumentado.**
  Candidato forte a avaliar: o
  [OpenTelemetry Demo (Astronomy Shop)](https://opentelemetry.io/docs/demo/) —
  é um e-commerce de referência oficial da comunidade OTel, multi-serviço,
  poliglota, já totalmente instrumentado, já sobe via `docker compose`, e
  já tem **feature flags para injetar falhas** (latência, erros, etc.) nos
  serviços. Pode economizar bastante trabalho de instrumentação manual —
  mas precisa validar se o formato de export dele é compatível com o
  pipeline OTel Collector → OpenObserve já existente, e se o conjunto de
  falhas disponíveis cobre os cenários que o time quer demonstrar.
- **Qual domínio simular.** Precisa bater com o tipo de incidente que o
  pitch quer demonstrar (ex.: e-commerce com falha de checkout, API com
  dependência externa instável, pipeline de dados com falha de
  processamento). O domínio influencia diretamente que tipos de causa raiz
  dá pra demonstrar.
- **Catálogo de cenários de falha** — este documento não define a lista
  final, mas aponta categorias a cobrir para ter diversidade (cada
  categoria testa um tipo diferente de correlação entre fontes):
  - Falha de código determinística (já existe um exemplo simples no
    `demo_app`).
  - Saturação de recurso de host (CPU ou RAM no limite, causando
    degradação/timeout).
  - Degradação de banco de dados (query lenta, lock, conexão esgotada).
  - Falha/latência de rede entre serviços (ex.: via `tc`/`toxiproxy` ou
    feature flag, se usar o OTel Demo).
  - Falha de dependência externa (timeout de uma API terceira simulada).
- **Como expor métricas de host.** Se for preciso CPU/RAM/disco dos
  containers, considerar o `hostmetrics`/`docker_stats` receiver do próprio
  OTel Collector (mantém tudo no mesmo pipeline) em vez de introduzir uma
  stack paralela (ex. Prometheus + cAdvisor), para não fragmentar os dados
  entre duas ferramentas de observabilidade diferentes.

## Entregáveis (Definition of Done desta frente)

1. Um `docker compose up` sobe o ambiente de referência completo
   (aplicação multi-serviço + banco + geração de métricas de host) e ele
   aparece no OpenObserve (mesma instância usada pelo resto do projeto).
2. Pelo menos 3 cenários de falha diferentes, de categorias distintas (ver
   lista acima), cada um ativável de forma determinística (comando,
   endpoint ou feature flag — não aleatório) e documentado: como ativar, o
   que deveria ser observável em logs/métricas/traces, e qual é a causa
   raiz "gabarito" (pra depois comparar com o que os agentes do TracePilot
   concluem).
3. Um `README.md` dentro da pasta do ambiente de referência explicando como
   subir, como disparar cada cenário, e o que esperar.

## Onde isso entra no repositório

Sugestão de organização (a confirmar com quem for implementar): uma pasta
nova na raiz, ex. `reference-env/`, com seu próprio `docker-compose.yml`
(serviços da aplicação simulada) apontando para o OTel Collector já
definido no `docker-compose.yml` da raiz — mantendo a stack de telemetria
(OpenObserve + Collector) como peça única e compartilhada entre
`demo_app/` e `reference-env/`.
