import asyncio, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright

BASE = Path(__file__).parent
SITES = [l.strip() for l in (BASE / "sites.txt").read_text().splitlines() if l.strip()]
SEM = asyncio.Semaphore(6)
SEL = ["#onetrust-banner-sdk", "#onetrust-consent-sdk", "#ot-sdk-btn", ".optanon-alert-box-wrapper"]
RX = re.compile(r"onetrust|cookielaw|optanon", re.I)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

async def check(browser, url, wait_ms=9000):
    async with SEM:
        ctx = await browser.new_context(ignore_https_errors=True, user_agent=UA)
        page = await ctx.new_page()
        net_hit = {"v": False}
        page.on("request", lambda r: net_hit.update(v=True) if "cookielaw.org" in r.url else None)
        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            await page.wait_for_timeout(wait_ms)
            if net_hit["v"]:
                return url, True
            for s in SEL:
                if await page.query_selector(s):
                    return url, True
            scripts = await page.eval_on_selector_all("script[src]", "els=>els.map(e=>e.src)")
            if any(RX.search(s) for s in scripts):
                return url, True
            if await page.evaluate("() => !!(window.OneTrust || window.Optanon || window.OptanonActiveGroups)"):
                return url, True
            if RX.search(await page.content()):
                return url, True
            return url, False
        except Exception:
            return url, None
        finally:
            await ctx.close()

def domain(url):
    return urlparse(url).netloc.replace("www.", "")

def build_html(fail, err, total):
    hoje = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y")
    ok_count = total - len(fail) - len(err)

    def buttons(urls, bg, border):
        rows = ""
        for u in urls:
            rows += f"""
            <tr><td style="padding:0 0 10px 0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr><td bgcolor="{bg}" style="border:1px solid {border};border-radius:6px;padding:12px 16px;">
                  <a href="{u}" target="_blank" style="color:#1a1a1a;text-decoration:none;font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:bold;display:block;">
                    &#128279;&nbsp; {domain(u)}
                  </a>
                </td></tr>
              </table>
            </td></tr>"""
        return rows

    if not fail and not err:
        status_block = """
        <tr><td align="center" style="padding:30px 20px;">
          <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
            <tr><td bgcolor="#e8f5e9" align="center" style="border:1px solid #a5d6a7;border-radius:8px;padding:28px;">
              <div style="font-size:40px;line-height:1;">&#9989;</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#1b5e20;padding-top:10px;">Tudo ok</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#2e7d32;padding-top:6px;">Todos os sites monitorados est&atilde;o em conformidade com o banner OneTrust.</div>
            </td></tr>
          </table>
        </td></tr>"""
    else:
        blocks = ""
        if fail:
            blocks += f"""
            <tr><td style="padding:20px 20px 5px 20px;">
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:bold;color:#b71c1c;">&#9888;&#65039; ALERTA &mdash; Sites fora de conformidade</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#666;padding:4px 0 14px 0;">Banner de cookies OneTrust n&atilde;o identificado. Clique para abrir o site.</div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{buttons(fail, "#fdecea", "#f5c6c0")}</table>
            </td></tr>"""
        if err:
            blocks += f"""
            <tr><td style="padding:10px 20px 5px 20px;">
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:bold;color:#e65100;">&#10060; Sites inacess&iacute;veis</div>
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#666;padding:4px 0 14px 0;">N&atilde;o foi poss&iacute;vel carregar. Verificar manualmente.</div>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">{buttons(err, "#fff3e0", "#ffcc80")}</table>
            </td></tr>"""
        status_block = blocks

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background-color:#f4f4f4;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" bgcolor="#f4f4f4">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;width:100%;">
    <!-- Header -->
    <tr><td bgcolor="#0d1b2a" style="border-radius:8px 8px 0 0;padding:22px 24px;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:20px;font-weight:bold;color:#ffffff;">&#128225; Banner Monitor</div>
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#9fb3c8;padding-top:4px;">Monitoria di&aacute;ria OneTrust &bull; {hoje}</div>
    </td></tr>
    <!-- Resumo -->
    <tr><td bgcolor="#ffffff" style="padding:18px 20px 0 20px;">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
          <td width="33%" align="center" bgcolor="#f5f7fa" style="border-radius:6px;padding:12px 4px;">
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:bold;color:#0d1b2a;">{total}</div>
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#666;">Monitorados</div>
          </td>
          <td width="8">&nbsp;</td>
          <td width="33%" align="center" bgcolor="#e8f5e9" style="border-radius:6px;padding:12px 4px;">
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:bold;color:#1b5e20;">{ok_count}</div>
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#2e7d32;">Conformes</div>
          </td>
          <td width="8">&nbsp;</td>
          <td width="33%" align="center" bgcolor="{'#fdecea' if (fail or err) else '#f5f7fa'}" style="border-radius:6px;padding:12px 4px;">
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:bold;color:{'#b71c1c' if (fail or err) else '#0d1b2a'};">{len(fail) + len(err)}</div>
            <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{'#b71c1c' if (fail or err) else '#666'};">Alertas</div>
          </td>
        </tr>
      </table>
    </td></tr>
    <!-- Status / Alertas -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" bgcolor="#ffffff" style="max-width:560px;width:100%;">
      {status_block}
    </table>
    <!-- Footer -->
    <tr><td bgcolor="#ffffff" align="center" style="border-radius:0 0 8px 8px;border-top:1px solid #eeeeee;padding:14px;">
      <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#999;">Gerado automaticamente pelo Banner Monitor &bull; Afya</div>
    </td></tr>
  </table>
</td></tr>
</table>
</body></html>"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = await asyncio.gather(*[check(browser, u) for u in SITES])
        pend = [u for u, ok in results if ok is not True]
        if pend:
            retry = await asyncio.gather(*[check(browser, u, wait_ms=18000) for u in pend])
            fixed = dict(retry)
            results = [(u, fixed.get(u, ok)) for u, ok in results]
        await browser.close()

    fail = [u for u, ok in results if ok is False]
    err = [u for u, ok in results if ok is None]

    if not fail and not err:
        msg = "Tudo ok."
    else:
        lines = []
        if fail:
            lines.append("⚠️ ALERTA — sites fora de conformidade OneTrust:")
            lines += [f"⚠️ {u}" for u in fail]
        if err:
            lines.append("❌ Sites inacessíveis (verificar manualmente):")
            lines += [f"❌ {u}" for u in err]
        msg = "\n".join(lines)

    print(msg)
    (BASE / "resultado.txt").write_text(msg)
    (BASE / "resultado.html").write_text(build_html(fail, err, len(SITES)), encoding="utf-8")

asyncio.run(main())
