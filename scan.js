#!/usr/bin/env node
/**
 * Monitoria diária do banner de cookies OneTrust.
 *
 * Abre cada site num Chromium headless, deixa o JavaScript rodar (inclusive GTM)
 * e verifica quatro sinais independentes de que o OneTrust está ativo.
 *
 * Uso:
 *   node scan.js                 # varredura completa
 *   node scan.js --site URL      # testa um site só (debug)
 *   node scan.js --headed        # abre o navegador na tela (debug)
 *
 * Variáveis de ambiente:
 *   SLACK_WEBHOOK_URL   webhook de entrada; se ausente, só imprime no console
 *   CONCURRENCY         abas em paralelo (padrão 5)
 *   NAV_TIMEOUT_MS      timeout de navegação (padrão 45000)
 *   SETTLE_MS           janela de espera pelo OneTrust após o load (padrão 12000)
 *   FAIL_EXIT           "1" faz o processo sair com código 1 se houver falha
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SITES = JSON.parse(fs.readFileSync(path.join(__dirname, 'sites.json'), 'utf8'));
const CONCURRENCY = Number(process.env.CONCURRENCY || 5);
const NAV_TIMEOUT = Number(process.env.NAV_TIMEOUT_MS || 45000);
const SETTLE_MS = Number(process.env.SETTLE_MS || 12000);
const OUT_DIR = path.join(__dirname, 'artifacts');
const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

const argv = process.argv.slice(2);
const oneSite = argv.includes('--site') ? argv[argv.indexOf('--site') + 1] : null;
const headed = argv.includes('--headed');
const targets = oneSite ? [oneSite] : SITES;

/** Sinais avaliados dentro da página, depois que o JS rodou. */
function probe() {
  const q = (s) => document.querySelector(s);
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const banner =
    q('#onetrust-banner-sdk') ||
    q('#onetrust-consent-sdk [role="dialog"]') ||
    q('.ot-sdk-container');
  return {
    sdkGlobal: typeof window.OneTrust !== 'undefined' || typeof window.Optanon !== 'undefined',
    consentSdkDom: !!q('#onetrust-consent-sdk'),
    otContainerDom: !!q('.ot-sdk-container'),
    bannerVisivel: visible(banner),
    grupos: window.OnetrustActiveGroups || null,
    titulo: document.title || '',
  };
}

async function checkSite(context, url) {
  const page = await context.newPage();
  const rec = {
    url,
    status: 'FALHA',
    http: null,
    sdkGlobal: false,
    consentSdkDom: false,
    otContainerDom: false,
    bannerVisivel: false,
    redeCookielaw: false,
    erro: null,
    screenshot: null,
  };

  // Sinal de rede: qualquer requisição ao CDN do OneTrust conta como prova de carga.
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('cookielaw.org') || u.includes('onetrust.com') || u.includes('otBannerSdk')) {
      rec.redeCookielaw = true;
    }
  });

  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
    rec.http = resp ? resp.status() : null;

    // Espera ativa: o GTM costuma injetar o OneTrust alguns segundos após o load.
    const deadline = Date.now() + SETTLE_MS;
    let p = await page.evaluate(probe);
    while (Date.now() < deadline && !(p.sdkGlobal || p.consentSdkDom || rec.redeCookielaw)) {
      await page.waitForTimeout(1000);
      p = await page.evaluate(probe);
    }
    Object.assign(rec, {
      sdkGlobal: p.sdkGlobal,
      consentSdkDom: p.consentSdkDom,
      otContainerDom: p.otContainerDom,
      bannerVisivel: p.bannerVisivel,
      grupos: p.grupos,
    });

    const conforme = rec.sdkGlobal || rec.consentSdkDom || rec.otContainerDom || rec.redeCookielaw;
    rec.status = conforme ? 'OK' : 'FALHA';

    if (!conforme) {
      const nome = url.replace(/[^a-z0-9]/gi, '_').slice(0, 60) + '.png';
      rec.screenshot = path.join('artifacts', nome);
      await page.screenshot({ path: path.join(OUT_DIR, nome), fullPage: false });
    }
  } catch (e) {
    rec.status = 'ERRO';
    rec.erro = String(e.message || e).split('\n')[0].slice(0, 160);
  } finally {
    await page.close().catch(() => {});
  }
  return rec;
}

async function pool(items, size, fn) {
  const out = [];
  let i = 0;
  const workers = Array.from({ length: Math.min(size, items.length) }, async () => {
    while (i < items.length) {
      const idx = i++;
      out[idx] = await fn(items[idx]);
      process.stdout.write(`  ${out[idx].status.padEnd(5)} ${items[idx]}\n`);
    }
  });
  await Promise.all(workers);
  return out;
}

function montarMensagem(res) {
  const falhas = res.filter((r) => r.status === 'FALHA');
  const erros = res.filter((r) => r.status === 'ERRO');
  const data = new Date().toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' });

  if (!falhas.length && !erros.length) {
    return { texto: `Tudo ok. ${res.length} sites com banner OneTrust ativo — ${data}`, alerta: false };
  }
  let t = `:warning: *Banner de cookies — não conformidade detectada* (${data})\n`;
  if (falhas.length) {
    t += `\n*Sem banner OneTrust (${falhas.length}):*\n`;
    t += falhas.map((r) => `• ${r.url}`).join('\n') + '\n';
  }
  if (erros.length) {
    t += `\n*Não verificados (erro de acesso) (${erros.length}):*\n`;
    t += erros.map((r) => `• ${r.url} — ${r.erro}`).join('\n') + '\n';
  }
  t += `\n${res.filter((r) => r.status === 'OK').length}/${res.length} em conformidade.`;
  return { texto: t, alerta: true };
}

async function enviarSlack(texto) {
  const hook = process.env.SLACK_WEBHOOK_URL;
  if (!hook) {
    console.log('\n[slack] SLACK_WEBHOOK_URL não definido — envio ignorado.');
    return;
  }
  const r = await fetch(hook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: texto }),
  });
  console.log(`\n[slack] HTTP ${r.status}`);
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  console.log(`Varrendo ${targets.length} site(s), ${CONCURRENCY} em paralelo...\n`);

  const browser = await chromium.launch({ headless: !headed });
  const context = await browser.newContext({
    userAgent: UA,
    locale: 'pt-BR',
    viewport: { width: 1366, height: 900 },
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: { 'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8' },
  });

  const res = await pool(targets, CONCURRENCY, (u) => checkSite(context, u));
  await browser.close();

  res.sort((a, b) => a.url.localeCompare(b.url));
  fs.writeFileSync(path.join(OUT_DIR, 'report.json'), JSON.stringify(res, null, 2));
  fs.writeFileSync(
    path.join(OUT_DIR, 'report.csv'),
    'url,status,http,sdk_global,dom_consent_sdk,dom_ot_container,banner_visivel,rede_cookielaw,erro\n' +
      res
        .map((r) =>
          [
            `"${r.url}"`, r.status, r.http ?? '', r.sdkGlobal, r.consentSdkDom,
            r.otContainerDom, r.bannerVisivel, r.redeCookielaw, `"${r.erro ?? ''}"`,
          ].join(',')
        )
        .join('\n')
  );

  const { texto, alerta } = montarMensagem(res);
  console.log('\n' + '-'.repeat(60) + '\n' + texto.replace(/\*/g, '') + '\n');
  await enviarSlack(texto);

  if (alerta && process.env.FAIL_EXIT === '1') process.exit(1);
})();
