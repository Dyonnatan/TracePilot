# Roteiro — vídeo de demonstração do TracePilot

Duração alvo: **~6 minutos**. Formato: tela + narração. Cortes marcados com ✂.

---

## Links

| Parte | Link | Observação |
|---|---|---|
| **Loja Apex** — vitrine | <http://localhost:8088/#/> | |
| Loja — produto | <http://localhost:8088/#/produto/1> | Teclado mecânico 75% |
| Loja — checkout | <http://localhost:8088/#/checkout> | precisa ter item no carrinho |
| **TracePilot** — landing | <http://localhost:8800/> | |
| Login | <http://localhost:8800/login> | `lucas@apexspace.com.br` / `apex2026` (já preenchido) |
| Jornada (início) | <http://localhost:8800/onboarding> | leva ao passo em que parou |
| 1 · Boas-vindas | <http://localhost:8800/onboarding/welcome> | |
| 2 · Seu sistema | <http://localhost:8800/onboarding/about> | |
| 3 · Instalação | <http://localhost:8800/onboarding/install> | |
| 4 · Repositórios | <http://localhost:8800/onboarding/repo> | |
| 5 · Conexão | <http://localhost:8800/onboarding/connectivity> | |
| 6 · Análise | <http://localhost:8800/onboarding/configuring> | avança sozinha |
| 7 · Resumo | <http://localhost:8800/onboarding/summary> | |
| **Painel** (monitoramento) | <http://localhost:8800/dashboard> | |
| Painel com o guia aberto | <http://localhost:8800/dashboard?tour=1> | ou botão **Guia** |
| Painel — vulnerabilidades | <http://localhost:8800/dashboard#vulnerabilidades> | |
| Painel — investigar | <http://localhost:8800/dashboard#investigar> | |
| Investigação pronta (pagamento) | <http://localhost:8800/investigations/c69acd0f3745> | plano B da cena 6 |
| **Chaos Control** (falhas) | <http://localhost:8090/> | Ligar / Desligar · Gabarito |
| OpenObserve (dados brutos) | <http://localhost:5080/web/> | `admin@tracepilot.local` / `ChangeMe123!` |
| TracePilot API — saúde | <http://localhost:8810/v1/health> | |
| TracePilot API — guia de integração | <http://localhost:8810/v1/guide> | |

Os links da jornada e do painel exigem login. Depois de clicar em **Iniciar monitoramento**, os links da
jornada levam ao painel. Para refazer a jornada, use **Refazer configuração** no rodapé do painel.

---

## Antes de gravar (checklist)

1. Subir tudo e conferir: `scripts/demo.sh up` → as 6 linhas com `ok`.
2. Começar a jornada do zero: `rm -f workspace/profile.json`.
3. Loja na versão boa e sem falhas ligadas:
   `cd demo_app && make deploy-good` · no Chaos Control (<http://localhost:8090>) tudo **Desligado**.
4. Deixar abertas, nesta ordem: **Loja** (<http://localhost:8088>), **TracePilot**
   (<http://localhost:8800>), **Chaos Control** (<http://localhost:8090>) e um **terminal** na raiz do repositório.
5. Escolher o tema (botão lua/sol no topo) antes de começar e não trocar no meio.
6. Ensaiar uma vez: a investigação com IA leva **~1,5 a 2 min** com o modelo local — no vídeo, corte (✂).
7. A linha do tempo da investigação cobre 24 h: testes feitos no mesmo dia aparecem nela. Para um vídeo
   limpo, grave longe de outros testes (ou aceite e comente: "aqui aparecem também os testes de mais cedo").

---

## Cena 1 — A aplicação de teste (0:00–0:40)

**Tela:** Loja Apex Space.
**Ações:** rolar a vitrine → abrir um produto → **Adicionar ao carrinho** → abrir o carrinho → **Finalizar pedido** com Pix.

> "Esta é a Apex Space, uma loja online criada com ajuda de IA — do jeito que muita gente cria sistemas hoje.
> Tem vitrine, carrinho, cupom de desconto e pagamento. Por trás, uma API da loja, um serviço de pagamento
> e um banco de dados. Um gerador de tráfego simula clientes comprando o tempo todo.
> Agora imagine que algo quebra às 23h de uma sexta. Quem não é especialista em servidor vê só isto:
> um erro 500 e um log que não diz nada."

---

## Cena 2 — O TracePilot (0:40–1:05)

**Tela:** <http://localhost:8800> (landing).
**Ações:** mostrar o título → rolar até o mapa de exemplo e **clicar numa caixa** → passar pelo "Antes e depois",
pela seção **Segurança** e por **Duas formas de conectar**.

> "O TracePilot vigia o site e o servidor, avisa antes de quebrar, aponta falhas de segurança e ataques —
> e, quando algo quebra, explica a causa em português, com um prompt pronto para a sua IA corrigir.
> Dá para conectar de duas formas: o TracePilot Collector, instalado no servidor, ou a TracePilot API,
> em que a própria aplicação envia os dados, sem instalar nada."

---

## Cena 3 — Configuração (1:05–2:15)

**Ações (é só avançar — tudo vem pré-preenchido):**

| Passo | O que mostrar | Fala curta |
|---|---|---|
| **Entrar** | login já preenchido (Lucas) | "Entro como o Lucas, dono da loja." |
| 1 · Boas-vindas | a lista de passos | "O TracePilot guia a configuração em poucos passos." |
| 2 · Seu sistema | nome, endereço e as opções clicáveis | "Quatro perguntas: nome, endereço, como foi feito, onde roda." |
| 3 · Instalação | as duas opções lado a lado | "Collector no servidor, API na aplicação. A loja já envia pela API via OpenTelemetry, e o Collector já está rodando nesta máquina." |
| 4 · Repositórios | os dois repositórios e o **+ Adicionar outro** | "Um ou vários repositórios: loja e pagamentos. Com o código, ele identifica tecnologias e checa segurança." |
| 5 · Conexão | as 4 linhas verdes | "Sistema no ar, Collector enviando, API recebendo, armazenamento online." |
| 6 · Análise | a animação (avança sozinha) | "Ele analisa a máquina, o sistema e a segurança…" |
| 7 · Resumo | **O que a análise encontrou** → **Segurança · o que corrigir primeiro** (abrir um item **Alto**) → mapa | "…e já mostra o que corrigir primeiro: por exemplo, uma senha padrão no banco. Cada item diz por que importa e como corrigir." |

**Ação final:** clicar em **Iniciar monitoramento**.

---

## Cena 4 — Monitoramento ativo (2:15–3:15)

**Tela:** painel. O **guia em balões** abre sozinho — avançar com **Próximo** narrando:

> - **Resumo:** "Como está o sistema agora: problemas, pontos de atenção e erros recentes."
> - **Mapa:** "Cada caixa é uma parte do sistema: usuários, site, banco, servidor."
> - **Conexão:** "Aqui ele mostra que está conectado, e por onde: Collector e API."
> - **Recursos:** "CPU, memória, disco, rede — o ponto de interrogação explica cada um em português."
> - **Alertas:** "Amarelo avisa antes de virar problema — o disco já está em atenção."
> - **Tráfego suspeito:** "Robôs e tentativas de invasão, ao vivo."
> - **Vulnerabilidades:** "As falhas de segurança por urgência, cada uma com um prompt para a IA corrigir."
> - **Investigar / Histórico / Ao vivo:** "E quando algo quebra, eu descrevo o problema com as minhas palavras."

---

## Cena 5 — Um ataque (3:15–3:50)

**Terminal:** `scripts/simulate-attack.sh`
**TracePilot (até 10 s):** a faixa do topo fica **vermelha** ("Tentativa de invasão…"), o nó **Usuários** ganha o
**✕**, e o cartão **Tráfego suspeito** lista sqlmap, Nuclei, `/.env`, Log4Shell, o IP e o que fazer.

> "Agora um robô tenta invadir a loja: procura arquivos esquecidos, tenta SQL injection, XSS.
> Em segundos o TracePilot identifica, separa robô de buscador legítimo, mostra o IP e diz o que fazer."

---

## Cena 6 — Erro 500 no pagamento (3:50–5:00)

1. **Chaos Control:** em **"Adquirente devolvendo 5XX em parte das autorizações"** → **Ligar**.
   > "Vou simular uma falha real: o processador de pagamentos começa a recusar parte das cobranças."
2. **Loja:** tentar **Finalizar pedido** (1 a 3 vezes até falhar) → aparece *"Não consegui concluir a operação"*.
   > "O cliente vê só isso."
3. **TracePilot (10–20 s):** alerta **"N erros nos últimos 15 min"**, o nó **Site / App** muda de cor.
   Clicar em **Investigar** (o texto já vem preenchido) → completar: *"cliente não consegue finalizar a compra, aparece erro"* → **Investigar**.
   > "Descrevo o problema como um cliente reclamaria."
4. ✂ **corte** (~1,5–2 min de investigação).
5. **Resultado:** ler a **causa** → mostrar **Onde o erro nasce**
   (`shop-api → … → payment-service → acquirer.charge` com `AcquirerUnavailable`) → **Linha do tempo** → **Prompt para a IA corrigir** (Copiar).
   > "O erro aparece na loja, mas nasce três saltos abaixo, no serviço de pagamento. O TracePilot seguiu o rastro
   > por todos os serviços até a origem — e entrega o prompt pronto para a IA corrigir."
6. *(Opcional)* No Chaos Control, abrir **Gabarito (causa raiz)**: "e bate com o gabarito do cenário."
7. **Desligar** o cenário.

---

## Cena 7 — O deploy que quebrou o cupom (5:00–5:50)

1. **Terminal:** `cd demo_app && make deploy-bad`
   > "Agora um deploy: a versão 1.1.0 da loja vai para o ar."
2. **Loja:** carrinho → **Cupom de desconto** `GRATIS100` → **Aplicar** (**3 ou 4 vezes**) → erro.
3. **TracePilot:** **Investigar** → *"o cupom GRATIS100 dá erro quando o cliente clica em Aplicar"*. ✂ **corte**.
4. **Resultado:** na **Linha do tempo**, apontar
   **"Deploy: shop-api 1.0.0 → 1.1.0 — com a versão nova, /cart/quote passou a falhar"** e a origem
   `pricing.quote` com `ZeroDivisionError`.
   > "Aqui entra o tempo: o TracePilot percebe que o erro começou junto com o deploy da versão nova,
   > e aponta a linha que divide por zero. Mesmo quando não há certeza absoluta, ele não para no
   > 'inconclusivo': vasculha a linha do tempo e entrega o melhor palpite, com a confiança."
5. **Terminal:** `make deploy-good` (volta a versão boa).

---

## Cena 8 — Fechamento (5:50–6:10)

**Tela:** painel de volta ao normal.

> "Monitoramento 24 horas, aviso antes de quebrar, segurança e investigação com IA que explica em
> português e entrega a correção. Para quem cria sistemas com IA e não quer virar especialista em
> servidor. Isso é o TracePilot."

---

## Plano B

- **Investigação demorando:** rode uma de cada cenário *antes* de gravar e, no vídeo, abra o resultado pelo **Histórico**.
- **Veio "Melhor palpite · N%" em vez de "Causa encontrada":** é o comportamento esperado quando a verificação não fecha — narre: "ele não para no inconclusivo".
- **Alerta não aparece:** clique em **atualizar** no topo do painel (o painel atualiza a cada 10 s).
- **Algum serviço fora:** `scripts/demo.sh status` e, se preciso, `scripts/demo.sh up` de novo.
- **Refazer a jornada:** no painel, **Refazer configuração** (ou `rm -f workspace/profile.json`).
