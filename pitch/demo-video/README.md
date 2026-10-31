# Gravação da apresentação

Grava o roteiro de [`pitch/roteiro-video.md`](../roteiro-video.md) direto dos
quatro painéis (TracePilot, loja Apex, Chaos Control e OpenObserve) com
Playwright, usando o Chrome do sistema. Cada cena vira um `.webm` próprio em
`out/raw` — os cortes (✂) do roteiro acontecem entre uma cena e outra, porque
as esperas longas (investigação com IA, deploy) ficam fora do vídeo.

A narração aparece como legenda na tela, junto de um cursor visível, então o
vídeo já sai assistível sem áudio.

## Antes

Tudo no ar (`scripts/demo.sh status` com as 6 linhas `ok`) e, uma vez só:

```bash
cd pitch/demo-video && npm install && npx playwright install ffmpeg
```

## Gravar

```bash
cd pitch/demo-video && node record.js
```

Só algumas cenas: `node record.js 5 6 7`. Ensaio rápido: `PACE=0.4 node record.js`.

| # | Cena | O que mostra |
|---|---|---|
| 1 | landing | a proposta do TracePilot, o mapa de exemplo, antes e depois |
| 2 | loja | a Apex Space funcionando: produto, carrinho, pedido com Pix |
| 3 | configuracao | login e a jornada inteira, até **Iniciar monitoramento** |
| 4 | painel | o painel com o guia em balões |
| 5 | falha | Chaos Control liga o erro 5XX do adquirente; o cliente vê o erro |
| 6 | investigar | o relato em português e a investigação disparada |
| 7 | resultado | causa, origem do erro, linha do tempo e prompt de correção |
| 8 | comparacao | tela dividida: OpenObserve cru × resposta do TracePilot |
| 9 | cenarios | o deploy que quebra o cupom e um ataque simulado |
| 10 | reacao | tráfego suspeito e alertas no painel; nova investigação |
| 11 | fechamento | o deploy na linha do tempo e o encerramento |

O script desliga os cenários (`payment_errors`, `coupon_bug`) ao terminar.

## Juntar

```bash
cd pitch/demo-video && ./compose.sh
```

Sai em `out/tracepilot-demo.mp4`. A cena 8 é montada lado a lado antes da
junção. Para regravar só uma cena, apague o `.webm` dela em `out/raw`, rode
`node record.js <n>` e depois `./compose.sh` de novo.

## Variáveis

`PACE` (1 = ritmo normal), `TP_URL`, `SHOP_URL`, `CHAOS_URL`, `OO_URL`.
As credenciais do OpenObserve vêm do `.env` da raiz.
