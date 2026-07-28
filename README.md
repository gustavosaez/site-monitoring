# Monitoria OneTrust — banner de cookies

Varredura diária dos sites da Afya para confirmar que o banner de consentimento
do OneTrust está ativo. Roda um Chromium headless via Playwright, executa o
JavaScript da página (inclusive GTM) e avalia o estado real do banner — não
apenas o HTML de origem.

## Por que Playwright e não curl

O OneTrust é injetado por GTM em boa parte dos sites. Uma verificação por
`curl` lê só o HTML inicial, onde o marcador ainda não existe, e produz falso
positivo de não conformidade. O Playwright espera o script rodar.

## Sinais avaliados

Um site é considerado **OK** se qualquer um destes for verdadeiro:

| Sinal | O que indica |
|---|---|
| `window.OneTrust` / `window.Optanon` | SDK carregado e inicializado |
| `#onetrust-consent-sdk` no DOM | container do OneTrust injetado |
| `.ot-sdk-container` no DOM | container da DIV padrão presente |
| requisição a `cookielaw.org` | o script foi efetivamente buscado no CDN |

Os campos `bannerVisivel` e `grupos` (`OnetrustActiveGroups`) vão no relatório
como informação complementar — úteis para investigar um site que carrega o SDK
mas não exibe o banner.

## Status possíveis

- `OK` — pelo menos um sinal positivo
- `FALHA` — página carregou, nenhum sinal de OneTrust (screenshot é salvo)
- `ERRO` — navegação falhou (timeout, DNS, TLS, bloqueio)

## Uso local

```bash
npm install                                   # instala Playwright + Chromium
npm run scan                                  # varredura completa
node scan.js --site https://afya.com.br/      # um site só
node scan.js --headed --site https://afya.com.br/   # com navegador na tela
```

Saídas em `artifacts/`: `report.json`, `report.csv` e os PNGs das falhas.

## Configuração no GitHub

1. Suba este diretório para um repositório.
2. Crie o webhook no Slack: <https://api.slack.com/messaging/webhooks> — app novo,
   ative *Incoming Webhooks*, aponte para o canal de privacidade/compliance.
3. Repositório → **Settings → Secrets and variables → Actions → New secret**
   - nome: `SLACK_WEBHOOK_URL`
   - valor: a URL do webhook
4. O workflow roda todo dia às 08:00 BRT. Para testar agora: aba **Actions** →
   *Monitoria OneTrust* → **Run workflow**.

Relatórios e screenshots ficam anexados a cada execução por 90 dias.

## Variáveis de ambiente

| Variável | Padrão | Função |
|---|---|---|
| `SLACK_WEBHOOK_URL` | — | destino do alerta; sem ela, só imprime no console |
| `CONCURRENCY` | `5` | abas simultâneas |
| `NAV_TIMEOUT_MS` | `45000` | timeout de navegação por site |
| `SETTLE_MS` | `12000` | janela de espera pelo OneTrust após o load |
| `FAIL_EXIT` | `0` | `1` faz o job falhar quando houver não conformidade |

## Manutenção

- **Adicionar ou remover site:** edite `sites.json`.
- **Site legítimo caindo como FALHA:** abra o screenshot em `artifacts/`. Se o
  banner aparece na imagem, aumente `SETTLE_MS` — o GTM daquele site demora mais.
- **`ERRO` recorrente por WAF:** rode `--headed` naquele site para ver o bloqueio.
  Alguns WAFs exigem um `User-Agent` ou origem de IP específicos.

## Formato do alerta

Tudo em conformidade:

```
Tudo ok. 51 sites com banner OneTrust ativo — 28/07/2026 08:00
```

Com problema:

```
⚠️ Banner de cookies — não conformidade detectada (28/07/2026 08:00)

Sem banner OneTrust (3):
• https://exemplo1.edu.br/
• https://exemplo2.edu.br/
• https://exemplo3.edu.br/

48/51 em conformidade.
```
