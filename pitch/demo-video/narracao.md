# Narração — para ler na gravação

Texto de locução do vídeo **`out/tracepilot-demo-5min.mp4`** (4 min 51 s).
Cada bloco cabe no tempo real da cena (corte de `compose-curto.sh`), lendo em
ritmo normal de conversa. `[tela]` é só referência — não se lê.

---

## 1 · 0:00–0:25 · A proposta
`[tela]` landing, mapa do sistema

> Seu sistema caiu. A gente diz por quê. Esse é o TracePilot.
>
> Ele vigia o site e o servidor, avisa antes de quebrar, aponta falhas de
> segurança e ataques.
>
> Este é o mapa: cada caixa é uma parte — usuários, site, banco, servidor.

## 2 · 0:25–0:52 · A loja
`[tela]` Apex Space: produto, carrinho, Pix

> Esta é a Apex Space: uma loja criada com ajuda de IA, do jeito que muita
> gente cria sistemas hoje.
>
> Vitrine, carrinho, cupom, pagamento. Por trás: API da loja, serviço de
> pagamento, banco de dados.
>
> Abro um produto, coloco no carrinho, finalizo com Pix. Tudo funcionando.
>
> Agora imagine que algo quebra às onze da noite de uma sexta.

## 3 · 0:52–1:24 · A configuração
`[tela]` login do Lucas e a jornada até **Iniciar monitoramento**

> Entro como o Lucas, dono da loja. O TracePilot guia a configuração em poucos
> passos.
>
> Nome do sistema, endereço, como foi feito, onde roda.
>
> Duas formas de conectar: o Collector no servidor, ou a API, sem instalar
> nada.
>
> Com o código do repositório, ele identifica as tecnologias e já checa a
> segurança.
>
> E mostra o que corrigir primeiro — como uma senha padrão no banco — com o
> prompt pronto para a IA.

## 4 · 1:24–1:50 · O painel
`[tela]` painel com o guia em balões

> Configurado. A partir daqui o painel mostra o sistema inteiro.
>
> Como ele está agora. O mapa dos serviços. CPU, memória, disco, rede,
> explicados em português.
>
> Alertas que avisam antes de virar problema. Tráfego suspeito, ao vivo.
> Vulnerabilidades por urgência.
>
> Agora vamos quebrar alguma coisa.

## 5 · 1:50–2:11 · A falha
`[tela]` Chaos Control, **Ligar** o 5XX do adquirente

> Este é o painel do apresentador: aqui eu ligo falhas reais.
>
> Vou ligar esta: o processador de pagamentos recusa parte das cobranças.
>
> Ligado. Nada disso aparece na telemetria — pro TracePilot é uma falha como
> outra qualquer.

## 6 · 2:11–2:26 · O cliente
`[tela]` loja, **Finalizar pedido** falhando

> Do outro lado, um cliente tenta fechar o pedido.
>
> E é isso que ele vê: "não consegui concluir a operação". Sem explicação.

## 7 · 2:26–2:42 · A investigação
`[tela]` erros no painel, relato sendo digitado

> Em segundos o painel acusa os erros, e o nó do site muda de cor.
>
> Descrevo o problema como um cliente reclamaria. A IA cruza logs, métricas e
> rastros de todos os serviços.

## 8 · 2:42–3:07 · A resposta
`[tela]` causa, origem, linha do tempo, prompt de correção

> A resposta, em português: a causa, e o que fazer agora.
>
> O erro aparece na loja, mas nasce no serviço de pagamento. Ele seguiu o
> rastro até a origem.
>
> A linha do tempo mostra quando começou. E entrega o prompt pronto: é só
> copiar e colar.

## 9 · 3:07–3:30 · Os dois lados
`[tela]` OpenObserve cru × resposta do TracePilot

> A mesma falha, vista dos dois lados.
>
> À esquerda, o dado cru: milhares de linhas.
>
> À direita, a mesma informação já lida: causa, origem, correção.
>
> Um lado é um banco de dados. O outro é uma resposta.

## 10 · 3:30–3:56 · Outros casos
`[tela]` deploy 1.1.0 subindo de verdade

> O ambiente tem outros casos, cada um com o gabarito da causa raiz.
>
> Este é um deploy: a versão um ponto um, que quebra o cupom de cem por cento.
> Sobe de verdade, como em produção.
>
> E, junto, um ataque: um robô varrendo a loja atrás de brechas.

## 11 · 3:56–4:06 · O cupom
`[tela]` cliente aplicando GRATIS100

> O cliente aplica o cupom e recebe, de novo, o mesmo erro.

## 12 · 4:06–4:25 · A reação
`[tela]` tráfego suspeito, alertas, nova investigação

> Em segundos, o painel reage aos dois.
>
> O ataque: separa robô de buscador legítimo, mostra a origem e o que fazer.
>
> O deploy quebrado vira alerta. Descrevo com minhas palavras e deixo a IA
> seguir o rastro.

## 13 · 4:25–4:51 · Fechamento
`[tela]` investigação do cupom e painel normal

> O erro começou junto com o deploy. A linha do tempo liga os dois e aponta a
> divisão por zero no preço.
>
> Mesmo sem certeza absoluta, ele não para no inconclusivo: entrega o melhor
> palpite, com a confiança.
>
> Monitoramento vinte e quatro horas. Segurança. Investigação com IA que
> explica e corrige.
>
> Isso é o TracePilot.

---

## Ajustes de tempo

- Ficou curto: alongue as pausas, nunca acelere.
- Ficou longo: corte a última frase do parágrafo — foram escritas como sobra
  sacrificável.
