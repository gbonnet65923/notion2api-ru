# Test mail.tm for Notion signup (fresh unique inboxes)
import asyncio, json, re, random, string, time
from playwright.async_api import async_playwright
import httpx

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
BASE = os.path.dirname(os.path.abspath(__file__))

def mailtm_create():
    firsts = ["alex", "maria", "peter", "laura", "stef", "anna", "tony", "nina", "eric", "sara", "luca", "jana", "tom", "lena", "paul", "kate"]
    with httpx.Client(timeout=20, trust_env=False) as c:
        r = c.get("https://api.mail.tm/domains")
        domain = r.json()["hydra:member"][0]["domain"]
        addr = random.choice(firsts) + random.choice(firsts) + str(random.randint(100, 999)) + "@" + domain
        pw = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        r = c.post("https://api.mail.tm/accounts", json={"address": addr, "password": pw})
        if r.status_code not in (200, 201):
            return None, None, None, r.text
        # token
        r2 = c.post("https://api.mail.tm/token", json={"address": addr, "password": pw})
        tok = r2.json().get("token")
        return addr, pw, tok, "ok"

def mailtm_wait_code(tok, deadline_s=200):
    t0 = time.time()
    headers = {"Authorization": f"Bearer {tok}"}
    with httpx.Client(timeout=20, trust_env=False, headers=headers) as c:
        while time.time() - t0 < deadline_s:
            try:
                r = c.get("https://api.mail.tm/messages")
                msgs = r.json().get("hydra:member", [])
                for m in msgs:
                    if "notion" in (m.get("from", {}).get("address", "") + m.get("subject", "")).lower():
                        # тело письма
                        r2 = c.get(f"https://api.mail.tm/messages/{m['id']}")
                        d = r2.json()
                        text = (d.get("text") or "") + " " + (d.get("subject") or "")
                        mm = re.search(r'\b([A-Za-z0-9]{6})\b', (d.get("text") or "")[:300])
                        if not mm:
                            lines = [l.strip() for l in (d.get("text") or "").splitlines() if l.strip()]
                            for l in lines[:5]:
                                if re.fullmatch(r'[A-Za-z0-9]{6,8}', l):
                                    return l
                        if mm:
                            return mm.group(1)
            except Exception as e:
                print("mailtm err:", str(e)[:100])
            time.sleep(5)
    return None

async def main():
    addr, pw, tok, st = mailtm_create()
    if not addr:
        print("MAILTM FAIL:", st)
        return
    print("MAILBOX:", addr)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
        page = await ctx.new_page()
        await page.goto("https://www.notion.so/signup", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        email_input = page.locator("input[type=email]").first
        await email_input.fill(addr)
        await page.wait_for_timeout(600)
        cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
        if await cont.count():
            await cont.click()
        await page.wait_for_timeout(6000)
        body = (await page.inner_text("body")).lower()
        if "problem" in body:
            print("REJECTED (problem signing up)")
            await page.screenshot(path=f"{BASE}/mailtm_rejected.png")
        elif "verification" in body or "code" in body:
            print("CODE SENT — waiting IMAP-less...")
            code = mailtm_wait_code(tok)
            print("CODE:", code)
            if code:
                code_input = page.locator("input[autocomplete=one-time-code], input[inputmode=numeric], input[name=code]").first
                if await code_input.count():
                    await code_input.fill(code)
                else:
                    inputs = page.locator("input")
                    cnt = await inputs.count()
                    for j in range(cnt):
                        inp = inputs.nth(j)
                        t = await inp.get_attribute("type") or ""
                        if t not in ("email", "password"):
                            await inp.fill(code)
                            break
                await page.wait_for_timeout(600)
                cont2 = page.get_by_role("button", name=re.compile("Continue", re.I)).first
                if await cont2.count():
                    await cont2.click()
                await page.wait_for_timeout(8000)
                body2 = (await page.inner_text("body")).lower()
                print("AFTER CODE URL:", page.url)
                print("AFTER CODE BODY:", body2[:300])
                await page.screenshot(path=f"{BASE}/mailtm_after_code.png")
                await ctx.storage_state(path=f"{BASE}/state_mailtm_test.json")
        else:
            print("UNKNOWN STATE:", body[:300])
            await page.screenshot(path=f"{BASE}/mailtm_unknown.png")
        await browser.close()

asyncio.run(main())
