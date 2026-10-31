# Benchmark — OpenRCA

Plano de avaliação (ainda não implementado nesta fase de scaffold).

## Objetivo

Medir, de forma comparável, a capacidade de identificar a causa-raiz de um
incidente em três configurações:

1. **LLM simples** — um único prompt com todo o contexto disponível.
2. **Agente único** — um agente com acesso a ferramentas de consulta
   (logs/métricas/traces), sem divisão de papéis.
3. **Multiagente** (TracePilot) — orquestrador + especialistas + diagnóstico
   + verificador.

## Benchmark

Usar o benchmark aberto **[OpenRCA](https://github.com/microsoft/OpenRCA)**
como base de casos de incidente com causa-raiz conhecida, para ter um
gabarito objetivo de comparação.

## Métricas

- Acurácia na identificação da causa-raiz.
- Tempo até o diagnóstico.
- Custo de inferência (tokens/chamadas de LLM).
- Fundamentação das evidências (o relatório cita evidências reais, não
  alucinadas).

## Status

Resultados ainda não medidos — este diretório existe para já reservar o
lugar do harness de avaliação quando a lógica dos agentes estiver
implementada (ver `docs/code-architecture.md`).
