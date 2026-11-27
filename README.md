# 🙏 MeditaBot Diário — IASD de Angra do Heroísmo ✨

Bot automático que, todos os dias, recolhe as três meditações do site **CPB Mais** e publica-as num canal do **Telegram** e num grupo do **WhatsApp**, sem intervenção manual.

## 🎯 Sobre o Projeto

O bot substitui a tarefa diária de copiar, formatar e colar as meditações. Acede ao site oficial, extrai o conteúdo, adapta a formatação a cada plataforma e publica-o de forma limpa para a comunidade da igreja.

Corre inteiramente no **GitHub Actions**, sem servidor próprio. O WhatsApp é controlado através do WhatsApp Web (biblioteca `whatsapp-web.js`), sem custos da API oficial da Meta.

## 🚀 Funcionalidades

* **Três meditações por dia:** Meditação Matinal, Meditação da Mulher e Meditação Jovem, com 3 tentativas por fonte.
* **Telegram:** cada meditação é publicada no canal com pré-visualização do vídeo do YouTube.
* **WhatsApp, uma mensagem por meditação:** a miniatura do vídeo aparece primeiro e, na legenda, o título, o texto e os links. A miniatura é descarregada de `img.youtube.com` (`maxresdefault`, com recurso a `hqdefault`). Se falhar, segue só o texto.
* **Mensagem de motivação diária:** 7 mensagens em rotação pelo dia de calendário (fuso de Lisboa).
  * Dois dias seguidos nunca recebem a mesma mensagem.
  * Cada mensagem repete-se só ao fim de 7 dias.
* **Sessão do WhatsApp persistente e cifrada:** é guardada como artefacto do GitHub Actions, cifrada com AES-256 e mantida por 90 dias. É renovada sempre que o login tem sucesso.
* **Login resiliente:** até 3 tentativas com browser novo.
  * A cópia desatualizada da app WhatsApp Web é limpa antes de cada execução.
  * Na última tentativa, a versão atual do WhatsApp Web é fixada automaticamente.
  * Cada tentativa falhada regista um diagnóstico da página.
* **Pareamento pelo telemóvel:** o QR Code é enviado como imagem para o seu Telegram pessoal.
* **Alertas de falha pelo bot no Telegram:** o seu chat pessoal recebe a causa e o link para os logs. Não há alertas por email.

## 🗂️ Estrutura do Código

| Ficheiro | Linguagem | Função |
| :--- | :--- | :--- |
| `meditacao_iasdah.py` | Python | Scraping das 3 meditações, publicação no Telegram, criação do payload do WhatsApp (`whatsapp_msg.txt`) e alerta único de falhas parciais. |
| `send_whatsapp.js` | Node.js | Login no WhatsApp Web (tentativas, diagnóstico, pareamento), envio das meditações com miniatura e mensagem de motivação. |
| `session_manager.py` | Python | Gestão da sessão do WhatsApp no CI: `restore`, `recuperar`, `health`, `clean`, `compress`, `clear`. |
| `alert_failure.py` | Python | Alerta no Telegram pessoal quando um passo do workflow falha. Distingue falha de login de falha de envio. |
| `.github/workflows/meditacao_diaria.yml` | YAML | Orquestração diária: sessão, dependências, publicação, alertas e gravação da sessão. |
| `versiculo_diario.py` | Python | Versículo do dia (14:00 de Lisboa): escolhe-o de `dados/versiculos_iasd_ara_5anos.json`, publica no Telegram e cria o payload do WhatsApp. |
| `.github/workflows/versiculo_diario.yml` | YAML | Orquestração do versículo diário, com os mesmos secrets e a mesma sessão WhatsApp. |
| `dados/versiculos_iasd_ara_5anos.json` | JSON | Plano de 5 anos: 1826 versículos ARA (`id`, `referencia`, `texto`, `tema`). |
| `tests/` | Python | Testes do versículo diário: `python -m unittest discover -s tests`. |
| `package.json` / `package-lock.json` | — | Dependências Node fixadas (instaladas com `npm ci`). |

## 🔧 Como Funciona

### 1. Scraping e Telegram — `meditacao_iasdah.py`

* Para cada fonte, descarrega a página com `requests` e extrai o conteúdo com `BeautifulSoup4` (até 3 tentativas, com 20 s de intervalo).
* Publica no canal do Telegram (MarkdownV2, com pré-visualização do vídeo).
* Acrescenta a versão limpa, sem escapes, a `whatsapp_msg.txt`, separando as meditações com `===DIVISAO_MEDITACAO===`. O ficheiro é recriado vazio no início de cada execução.
* Se alguma meditação falhar, envia **um único alerta** ao chat pessoal com o estado de cada uma, os detalhes do erro e o link para os logs.

### 2. WhatsApp — `send_whatsapp.js`

**`autenticar()`**: até 3 tentativas, cada uma com um `Client` novo (`LocalAuth` em `./whatsapp_auth`).

| Mecanismo | Detalhe |
| :--- | :--- |
| Timeout da biblioteca | `authTimeoutMs` de 120 s, para carregar a app e ligar o socket. |
| Watchdog | 260 s por tentativa, rearmado com sinais de progresso (`loading_screen`, `authenticated`). |
| Falha rápida | Se a app recarregar e a re-injeção da biblioteca falhar (`auth timeout`), a tentativa termina de imediato. |
| Diagnóstico | Uma tentativa falhada regista rota, título, versão do WhatsApp Web e indicadores de QR, lista de conversas ou ecrã de atualização. Nunca regista conteúdo de conversas nem capturas de ecrã. |
| Libertação do browser | Entre tentativas, o Chromium é terminado à força e os `Singleton*` são removidos (evita "browser is already running"). |
| Versão do WhatsApp Web | Sem pin por omissão. Na **última** tentativa, fixa automaticamente a versão *current* do [catálogo wppconnect](https://wppconnect.io/whatsapp-versions). |
| Sessão expirada | É gerado um QR Code, enviado como imagem para o Telegram pessoal, com 5 minutos para o scan. |

**`executarEnvio(client)`**
1. Lê o payload e envia cada meditação como mensagem única (miniatura com o texto na legenda), com até 3 tentativas e 20 s entre publicações.
2. Envia a mensagem de motivação do dia.
3. Encerra o cliente de forma controlada.

## 🗓️ Fluxo Diário no GitHub Actions

Ficheiro: `.github/workflows/meditacao_diaria.yml`.

* **Agendamento:** `cron: '13 0 * * *'` (00:13 UTC). O scheduler do GitHub não tem SLA e as execuções costumam arrancar várias horas depois.
* **Disparo manual:** *Run workflow*, com a opção **pareamento**.
* **Limites:** `timeout-minutes: 30`, e `concurrency` impede duas execuções em paralelo.

| # | Passo | O que faz |
| :--- | :--- | :--- |
| 1 | Ambiente | Python 3.10, Node.js 22 (cache npm), locale `pt_PT.UTF-8`. |
| 2 | Restaurar sessão WhatsApp | Descarrega o artefacto `whatsapp-session` mais recente e não expirado (seja qual for o resultado do run que o criou) e decifra-o com `WHATSAPP_SESSION_KEY`. |
| 3 | Extrair e validar sessão | `session_manager.py restore` (ou `recuperar`); remove locks `Singleton*` antigos. |
| 4 | Instalar dependências | `pip install` com versões fixas + `npm ci`. |
| 5 | Publicar Telegram | `python meditacao_iasdah.py` (saltado em modo pareamento). |
| 6 | Enviar WhatsApp | `node send_whatsapp.js`. |
| 7 | Alerta de falha | `python alert_failure.py`, apenas se um passo falhar. |
| 8 | Guardar sessão | Só se **esta** execução autenticou (marcador `.session_fresh`), mesmo que o envio tenha falhado: `clean` → `compress` → cifra AES-256 → artefacto `whatsapp-session` (90 dias). |

Uma sessão revogada nunca é guardada por cima da última sessão boa.

### Versículo diário — `.github/workflows/versiculo_diario.yml`

* **Lançamento oficial: 01-01-2027** (`VERSICULOS_DATA_INICIO`), com o versículo n.º 1.
* **Fase de teste (até ao lançamento):** o workflow das meditações envia o versículo do dia **só para o chat pessoal do administrador** (passo *Versículo diário (teste…)*, que nunca falha o job). O workflow das 14:00 não publica nada; corrido à mão, também envia só para o administrador.
* **Agendamento (depois do lançamento):** 14:00 de Lisboa. O cron é em UTC e Portugal muda de hora, por isso há dois crons (13:00 e 14:00 UTC); o job `horario` deixa passar só o que corresponde às 14:00 de Lisboa nesse dia. Também aqui o GitHub pode atrasar o arranque.
* **Escolha:** índice = (dias desde `VERSICULOS_DATA_INICIO`, data de Lisboa) mod 1826. Sem estado: re-execuções no mesmo dia repetem o versículo; o ciclo recomeça sozinho ao fim de 5 anos.
* **Envio:** `versiculo_diario.py` publica no canal Telegram e escreve `whatsapp_msg.txt`; `send_whatsapp.js` envia-o ao grupo com `WHATSAPP_MOTIVACAO=0` (sem a mensagem de motivação da manhã).
* **Sessão:** restaura e guarda o mesmo artefacto `whatsapp-session`. Usa o mesmo grupo de `concurrency` das meditações, por isso os dois workflows nunca correm em simultâneo. O pareamento continua a ser feito no workflow das meditações.
* **Teste local:** `python versiculo_diario.py --dry-run [--data AAAA-MM-DD]`.

## ⚙️ Configuração

### Secrets (`Settings > Secrets and variables > Actions > Secrets`)

| Secret | Descrição |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Token do bot, fornecido pelo `@BotFather`. |
| `TELEGRAM_CHAT_ID` | ID do canal/grupo do Telegram onde as meditações são publicadas (ex.: `-100XXXXXXXXXX`). |
| `TELEGRAM_PERSONAL_CHAT_ID` | O seu ID pessoal (via `@userinfobot`). Recebe os alertas de falha e o QR Code de pareamento. |
| `WHATSAPP_GROUP_ID` | ID do grupo do WhatsApp (ex.: `1203630XXXXXXXXX@g.us`). |
| `WHATSAPP_SESSION_KEY` | Chave aleatória longa que cifra a sessão guardada. Gere-a com `openssl rand -base64 48`. |

Mudar a `WHATSAPP_SESSION_KEY` torna ilegíveis as sessões já guardadas e obriga a novo pareamento.

### Variáveis opcionais (`Settings > Secrets and variables > Actions > Variables`)

| Variável | Descrição |
| :--- | :--- |
| `VERSICULOS_DATA_INICIO` | Dia em que é publicado o versículo n.º 1 (`AAAA-MM-DD`). Por omissão `2027-01-01` (lançamento oficial; antes disso, só testes no chat do administrador). |
| `WHATSAPP_WEB_VERSION` | Fixa a versão do WhatsApp Web em todas as tentativas (ex.: `2.3000.1056418802-alpha`). É um recurso de emergência; por omissão, deixe-a por definir. |

## 🔐 Pareamento do WhatsApp (QR Code)

É necessário na primeira utilização ou quando a sessão é revogada. O alerta de falha indica quando isto acontece.

1. Em **Actions**, escolha *Publicar Meditação Diária…* → **Run workflow** e marque **pareamento**.
2. O QR Code chega como imagem ao seu **Telegram pessoal** em poucos segundos. Também aparece no log do passo **Enviar WhatsApp**.
3. No telemóvel, abra o WhatsApp: **Definições > Dispositivos ligados > Ligar um dispositivo**, e leia o QR (válido cerca de 60 s; os seguintes chegam automaticamente, com 5 min no total).
4. A nova sessão é cifrada e guardada. Neste modo nada é publicado e o perfil antigo nunca é apagado: se o QR não for lido, a última sessão guardada mantém-se.

Para manter a ligação ativa, o telemóvel principal deve ficar online pelo menos uma vez a cada 14 dias.

## 💻 Execução Local

Requer Python 3.10+, Node.js 22 e um ambiente isolado (venv):

```bash
git clone https://github.com/IASD-AH/meditacao_iasdah.git
cd meditacao_iasdah
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install requests==2.32.5 beautifulsoup4==4.14.2 urllib3==2.5.0
npm ci
```

Pareamento local (apenas autentica e guarda a sessão em `./whatsapp_auth`):

```bash
WHATSAPP_PAREAMENTO=1 node send_whatsapp.js
```

A sessão local fica no seu computador; o bot na nuvem usa apenas a sessão guardada no Actions.

## 🛠️ Manutenção

* **Versão do `whatsapp-web.js`:** está fixada ao commit [`38eb45b`](https://github.com/wwebjs/whatsapp-web.js/commit/38eb45b2759450cc6fccb6a7a3f2cbc3bdb87db2) do repositório oficial. Esse commit contém a correção [#201990](https://github.com/wwebjs/whatsapp-web.js/pull/201990) para as versões recentes do WhatsApp Web, que ainda não saiu numa versão do npm. Quando sair uma versão do npm com essa correção, troque em `package.json` e regenere o `package-lock.json`.
* **Atualizações do WhatsApp Web:** o WhatsApp publica várias versões por dia. Se o login falhar:
  * procure a linha `Diagnóstico da página` nos logs;
  * como recurso temporário, defina `WHATSAPP_WEB_VERSION` com a versão *current* do catálogo wppconnect.
* **Tamanho da sessão:** cerca de 50 MB, a crescer com o histórico de conversas guardado pelo WhatsApp Web. As caches da app não são guardadas.
* **Artefactos:** cada login bem-sucedido cria um novo artefacto `whatsapp-session` (90 dias); é restaurado o mais recente.
* **Segurança:**
  * O repositório é **público**: qualquer utilizador do GitHub pode descarregar artefactos e ler os logs. Por isso a sessão é sempre cifrada e os diagnósticos nunca incluem conteúdo de conversas.
  * Nunca faça commit de `whatsapp_auth/`, `whatsapp-session.tar.gz*` nem `.env`; o `.gitignore` já os exclui.

E pronto: o MeditaBot publica todos os dias, de forma automática, para a comunidade da igreja de Angra do Heroísmo em ambas as plataformas. 🎉
