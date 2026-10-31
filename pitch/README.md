# Pitch

Abra [index.html](index.html) no navegador. Palco 16:9. A primeira abertura baixa a fonte IBM Plex. Depois disso o arquivo funciona com o cache do navegador.

Não há demo ao vivo dentro dos 3 minutos. O passo a passo do laboratório está no comentário `ROTEIRO_DEMO`, no fim de `index.html`.

## Atalhos

- Setas, espaço ou Enter: próximo slide. Seta esquerda: anterior.
- N ou S: roteiro falado.
- T: cronômetro, comparado com 3:00. Fica âmbar aos 2:45 e vermelho aos 3:00. R zera.
- F: tela cheia.
- ESC: os 8 slides reduzidos. Clique num deles para abrir.

## Ordem

| Slide | Tempo | O que dizer |
|---|---|---|
| 1 O que faz | 0:00–0:10 | O TracePilot investiga por você quando algo quebra. Diz a causa, a prova e entrega um texto para a IA corrigir. |
| 2 Mercado | 0:10–0:48 | Quem paga, por que agora, a frase dos vibe-coders, e o OpenRCA: 11,34% publicado, medição nossa em andamento. |
| 3 Solução | 0:48–1:08 | Ecossistema: aplicação, servidor e usuário já funcionam. Segurança é a próxima fase. Avisa, investiga, apoia a correção. |
| 4 Progresso | 1:08–1:38 | Feito hoje. Horas não cronometradas. Finalizar pedido, a mensagem da loja, Reportar problema. |
| 5 Arquitetura | 1:38–2:02 | Coletor, API, OpenTelemetry, OpenObserve, orquestrador e especialistas. A issue está no desenho; ainda não abre. |
| 6 Concorrentes | 2:02–2:22 | Sentry e Datadog também têm IA. A aposta é linguagem de quem não é SRE, o prompt e os dados sob controle. |
| 7 Mercado | 2:22–2:36 | US$ 10 bi → 23 bi, com fonte. Recorte: vibe-coders, software houses, startups. Preço é hipótese. |
| 8 Time | 2:36–3:00 | Por que nós, e o que o AKCIT Camp acelera: segurança, OpenRCA, roteamento e instalador. |

## Roteiro

O mesmo texto que a tecla N abre no slide. Cada bloco cabe no intervalo da esquerda.

**1 · 0:00–0:10.** O TracePilot investiga por você quando algo quebra. Ele diz o que quebrou, mostra a prova e entrega um texto para a sua IA corrigir. Hoje a história é uma compra que não termina.

**2 · 0:10–0:48.** Quem sofre é a dev sem especialista. Quem paga é o dono do sistema: o cliente, o desenvolvedor ou até mesmo as grandes empresas. Por que agora: a liberdade do uso de IA aumenta a quantidade de código e diminui a sua qualidade. Sexta, fim do dia, o cliente vê: “Não consegui concluir a operação.” A loja pede para tentar de novo e reportar ao time. Uma hora depois, ela ainda não sabe o que quebrou. Vibe-coders, software houses e startups colocam software no ar sem Site Reliability Engineering, o SRE, e sem especialista em segurança. A referência é o OpenRCA, da Microsoft, no ICLR 2025. 335 falhas, três sistemas, mais de 68 GB. O melhor publicado acerta 11,34%. Não é o nosso. A medição do TracePilot está em andamento. A tese é mais acerto e menos texto enviado ao modelo, porque cada especialista filtra e só o resumo sobe. Na nossa máquina, uma passagem levou cerca de 45 segundos e a decisão do verificador cerca de 300 milissegundos. Isso não é o resultado do teste.

**3 · 0:48–1:08.** A solução vigia o ecossistema. Aplicação, servidor e o caminho do usuário já funcionam. Segurança, login, arquivos e comandos, é a próxima fase, com o Wazuh, sempre opt-in. O ciclo é avisa, investiga e apoia a correção, com um texto para a mesma IA que escreveu o código consertar.

**4 · 1:08–1:38.** Isso já funciona, e foi feito hoje. As horas a gente não cronometrou. Olha a loja. Ela clica em finalizar o pedido. A tela diz a frase que você já viu. Ela reporta: “tentei comprar e não deu”. O relatório mostra a causa, o que fazer e o texto para a IA corrigir. Quanto tempo a investigação leva, a gente ainda não mediu.

**5 · 1:38–2:02.** Por baixo, um time de agentes. A telemetria entra pelo coletor em Rust, de cerca de 2 MB, pela API de quem não instala nada, ou por OpenTelemetry. O orquestrador chama logs, métricas e traces. O diagnóstico junta as hipóteses. O verificador tenta derrubá-las. Sai um resumo, um relatório e um texto de correção. A issue no GitHub está no desenho como opcional; hoje a gente ainda não abre. Os agentes só leem. O modelo pode ficar na máquina ou na nuvem. Quem decide a correção é a pessoa.

**6 · 2:02–2:22.** Sentry e Datadog também têm IA de causa. Seer e Bits AI. Eles servem quem já é desenvolvedor ou SRE, dentro da plataforma deles. A nossa aposta é outra: linguagem de quem não é SRE, o texto de correção para a IA de código de vocês, e os dados sob o controle de vocês.

**7 · 2:22–2:36.** O mercado de observabilidade vai de cerca de 10 para 23 bilhões de dólares até 2031, fonte MarketsandMarkets. O recorte nosso é vibe-coder, software house e startup. O modelo é hipótese: núcleo aberto, assinatura por serviço e uma versão gerenciada. O preço se valida na mentoria.

**8 · 2:36–3:00.** Somos duas pessoas. As duas técnicas. Dyonnatan mede modelo. Visão, linguagem, uma competição internacional, e o EstimaNutri. Ele construiu este protótipo. Lucas colocou software no ar, de equipamento conectado a crédito. Passou pela bxblue e pela Verde, da Y Combinator, e pela Locaweb. Por que nós: um já mediu modelos de IA, o outro já sustentou incidente em produção. Aprendemos que solução plausível não basta: diagnóstico tem de ter evidência verificável. No AKCIT Camp a gente busca validar o problema com quem publica software, construir a camada de segurança com privacidade, e definir o produto acessível. Os próximos passos são a segurança, o teste OpenRCA, o roteamento e o instalador. Obrigado.

## Prints

- Slide 4, esquerda: `img/landing.png`, a página inicial.
- Slide 4, direita: `img/relatorio.png`, a investigação da compra. O texto é o gabarito do cenário `payment_latency`, montado no template real. Não é uma passagem medida do agente.
