# Notion autoreg FINAL: Voidash inbox -> Notion signup -> code -> onboarding -> session
# Usage: python notion_reg.py N
import asyncio, json, re, sys, time, random, string, os
import httpx
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = BASE + "/accounts.jsonl"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
VOIDASH_DOMAINS = ["voidash.bond"]
NOTION_SIGNUP = "https://www.notion.so/signup"

FIRSTS = ["alex", "maria", "peter", "laura", "stef", "anna", "tony", "nina", "eric", "sara", "luca", "jana", "tom", "lena", "paul", "kate"]


def voidash_create():
    """Создать ящик Voidash. Возвращает (address, session_key) или (None, err)."""
    domain = random.choice(VOIDASH_DOMAINS)
    with httpx.Client(timeout=25, trust_env=False) as c:
        r = c.post("https://api.voidash.com/api/v1/inboxes", json={"domain": domain})
        if r.status_code not in (200, 201):
            return None, f"voidash {r.status_code}: {r.text[:100]}"
        d = r.json()
        return d["address"], d["session_key"]


def voidash_wait_code(session_key, deadline_s=240, since_ts=None):
    """Ждать код Notion в Voidash inbox. Возвращает код или None."""
    t0 = time.time()
    if since_ts is None:
        since_ts = t0
    headers = {"Authorization": f"Bearer {session_key}"}
    with httpx.Client(timeout=25, trust_env=False, headers=headers) as c:
        while time.time() - t0 < deadline_s:
            try:
                r = c.get("https://api.voidash.com/api/v1/messages")
                if r.status_code == 200:
                    msgs = r.json()
                    if isinstance(msgs, dict):
                        msgs = msgs.get("messages", msgs.get("data", []))
                    for m in msgs:
                        try:
                            created = m.get("created_at") or m.get("received_at") or ""
                            if created and since_ts:
                                # iso timestamp
                                from datetime import datetime, timezone
                                cts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
                                if cts < since_ts - 120:
                                    continue
                        except Exception:
                            pass
                        subj = (m.get("subject") or "").lower()
                        frm = json.dumps(m.get("from", {})).lower()
                        body_preview = (m.get("body") or m.get("text") or m.get("body_preview") or "")[:200]
                        if "notion" in subj or "notion" in frm:
                            full_body = m.get("body") or m.get("text") or ""
                            if not full_body:
                                # fetch single message
                                try:
                                    r2 = c.get(f"https://api.voidash.com/api/v1/messages/{m['id']}")
                                    full_body = r2.json().get("body") or r2.json().get("text") or ""
                                except Exception:
                                    pass
                            text = subj + "\n" + full_body
                            m2 = re.search(r'(?:code is|code:)\s*[:\s]*([A-Za-z0-9]{5,8})\b', text, re.I)
                            if not m2:
                                lines = [l.strip() for l in full_body.splitlines() if l.strip()]
                                for l in lines[:4]:
                                    if re.fullmatch(r'[A-Za-z0-9]{6,8}', l):
                                        return l
                            if not m2:
                                m2 = re.search(r'\b([A-Za-z0-9]{6})\b', full_body[:200])
                            if m2:
                                return m2.group(1)
            except Exception as e:
                print("voidash err:", str(e)[:120])
            time.sleep(6)
    return None


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    for i in range(n):
        print(f"=== reg {i+1}/{n} ===")
        res = await register_one()
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        print("RESULT:", json.dumps(res, ensure_ascii=False)[:700])


async def register_one():
    res = {"status": "error", "step": "init"}
    # 1) mailbox
    addr, key = voidash_create()
    if not addr:
        res["error"] = key
        return res
    res["email"] = addr
    res["voidash_key"] = key
    print("MAILBOX:", addr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1366, "height": 900})
        page = await ctx.new_page()
        try:
            await page.goto(NOTION_SIGNUP, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            # 2) email
            email_input = page.locator("input[type=email]").first
            await email_input.fill(addr)
            await page.wait_for_timeout(600)
            cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
            if await cont.count():
                await cont.click()
            else:
                await email_input.press("Enter")
            res["step"] = "email-submitted"
            await page.wait_for_timeout(5000)
            body = (await page.inner_text("body")).lower()
            if "invalid email domain" in body or "problem" in body:
                res["error"] = "rejected: " + body[:150]
                await page.screenshot(path=f"{BASE}/err_{int(time.time())}.png")
                return res

            # 3) verification code
            if "verification" in body or "code" in body:
                res["step"] = "await-otp"
                print("waiting for code...")
                sent_ts = time.time()
                code = await asyncio.to_thread(voidash_wait_code, key, 240, sent_ts)
                if not code:
                    res["error"] = "otp-not-found"
                    await page.screenshot(path=f"{BASE}/err_{int(time.time())}.pxng" if False else f"{BASE}/err_{int(time.time())}.png")
                    return res
                res["otp"] = code
                print("CODE:", code)
                code_input = page.locator("input[autocomplete=one-time-code], input[inputmode=numeric], input[name=code]").first
                if await code_input.count():
                    await code_input.fill(code)
                else:
                    inputs = page.locator("input")
                    cnt = await inputs.count()
                    filled = False
                    for j in range(cnt):
                        inp = inputs.nth(j)
                        t = await inp.get_attribute("type") or ""
                        ph = (await inp.get_attribute("placeholder") or "").lower()
                        if t not in ("email", "password") and "mail" not in ph:
                            await inp.fill(code)
                            filled = True
                            break
                    if not filled:
                        cells = page.locator("input[maxlength=1]")
                        cc = await cells.count()
                        for j, ch in enumerate(code):
                            if j < cc:
                                await cells.nth(j).fill(ch)
                await page.wait_for_timeout(600)
                cont2 = page.get_by_role("button", name=re.compile("Continue", re.I)).first
                if await cont2.count():
                    await cont2.click()
                await page.wait_for_timeout(7000)
                res["step"] = "code-submitted"

            # 4) password (если требуется)
            body = (await page.inner_text("body")).lower()
            pw_input = page.locator("input[type=password]").first
            if "password" in body and await pw_input.count():
                pw = "Not!" + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                res["password"] = pw
                res["step"] = "password-step"
                await pw_input.fill(pw)
                await page.wait_for_timeout(400)
                cont3 = page.get_by_role("button", name=re.compile("Continue|Sign up|Create", re.I)).first
                if await cont3.count():
                    await cont3.click()
                else:
                    await pw_input.press("Enter")
                await page.wait_for_timeout(7000)

            # 5) workspace + onboarding loop
            for attempt in range(12):
                body = (await page.inner_text("body")).lower()
                if "customize your profile" in body or "your name" in body:
                    res["step"] = f"profile-{attempt}"
                    await handle_profile(page)
                    await page.wait_for_timeout(3000)
                    continue
                if "create" in body and "workspace" in body:
                    res["step"] = f"workspace-{attempt}"
                    btn = page.get_by_role("button", name=re.compile("Create new workspace", re.I)).first
                    if await btn.count():
                        await btn.click()
                        await page.wait_for_timeout(4000)
                        continue
                if "what should we call" in body or "what would you like" in body or "name your" in body or "getting started" in body:
                    res["step"] = f"onboarding-{attempt}"
                    await handle_onboarding(page)
                    await page.wait_for_timeout(3000)
                    continue
                break

            res["final_url"] = page.url
            res["body_final"] = (await page.inner_text("body")).lower()[:300]
            state_path = f"{BASE}/state_{addr.replace('@', '_at_').replace('.', '_')}.json"
            await ctx.storage_state(path=state_path)
            res["state_path"] = state_path
            if "signup" not in page.url and "login" not in page.url and "appeals" not in page.url:
                res["status"] = "ok"
            else:
                res["status"] = "incomplete"
            await page.screenshot(path=f"{BASE}/final_{int(time.time())}.png")
        except Exception as e:
            res["error"] = str(e)[:300]
            try:
                await page.screenshot(path=f"{BASE}/err_{int(time.time())}.png")
            except Exception:
                pass
        finally:
            await browser.close()
    return res


async def handle_profile(page):
    # "Customize your profile" — "Your name" input + Continue
    name_inputs = page.locator("input[type=text], input:not([type]), input[name=name], input[placeholder*='name' i]")
    cnt = await name_inputs.count()
    for j in range(min(cnt, 1)):
        await name_inputs.nth(j).fill(random.choice(FIRSTS).capitalize() + " " + random.choice(FIRSTS).capitalize())
    cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
    if await cont.count():
        await cont.click()
    await page.wait_for_timeout(3000)


async def handle_onboarding(page):
    text_inputs = page.locator("input[type=text], input:not([type])")
    cnt = await text_inputs.count()
    filled = 0
    for j in range(min(cnt, 2)):
        inp = text_inputs.nth(j)
        try:
            ph = (await inp.get_attribute("placeholder") or "").lower()
        except Exception:
            ph = ""
        if "name" in ph or "call" in ph:
            await inp.fill("Alex")
            filled += 1
        elif "workspace" in ph or "team" in ph:
            await inp.fill("My Workspace")
            filled += 1
        elif filled == 0:
            await inp.fill("Alex")
            filled += 1
    radios = page.locator("input[type=radio]")
    rc = await radios.count()
    if rc:
        await radios.first.check()
    cont = page.get_by_role("button", name=re.compile("Continue|Next|Get started|Create", re.I)).first
    if await cont.count():
        await cont.click()
    await page.wait_for_timeout(2500)


if __name__ == "__main__":
    asyncio.run(main())
