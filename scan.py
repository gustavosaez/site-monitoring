import asyncio, re
from pathlib import Path
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

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = await asyncio.gather(*[check(browser, u) for u in SITES])
        # retry com espera estendida nos reprovados/erros
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

asyncio.run(main())
