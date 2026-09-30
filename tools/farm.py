# Notion Opus/GPT-6.1 free farm — FULL PIPELINE
# 1. Voidash mailbox  2. Signup + code  3. Onboarding  4. Model select + test message
# Usage: python farm.py N [model]
import asyncio, json, re, sys, time, random, string, os
import httpx
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = BASE + "/farm_accounts.jsonl"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
VOIDASH_DOMAINS = ["voidash.bond"]
NOTION_SIGNUP = "https://www.notion.so/signup"
FIRSTS = ["alex", "maria", "peter", "laura", "stef", "anna", "tony", "nina", "eric", "sara", "luca", "jana", "tom", "lena", "paul", "kate"]


def voidash_create():
    domain = random.choice(VOIDASH_DOMAINS)
    with httpx.Client(timeout=25, trust_env=False) as c:
        r = c.post("https://api.voidash.com/api/v1/inboxes", json={"domain": domain})
        if r.status_code not in (200, 201):
            return None, f"voidash {r.status_code}: {r.text[:100]}"
        d = r.json()
        return d["address"], d["session_key"]


def voidash_wait_code(session_key, deadline_s=240, since_ts=None):
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
                            created = m.get("created_at") or ""
                            if created and since_ts:
                                from datetime import datetime, timezone
                                cts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
                                if cts < since_ts - 120:
                                    continue
                        except Exception:
                            pass
                        subj = (m.get("subject") or "").lower()
                        frm = json.dumps(m.get("from", {})).lower()
                        if "notion" in subj or "notion" in frm:
                            full_body = m.get("body") or m.get("text") or ""
                            if not full_body:
                                try:
                                    r2 = c.get(f"https://api.voidash.com/api/v1/messages/{m['id']}")
                                    full_body = r2.json().get("body") or r2.json().get("text") or ""
                                except Exception:
                                    pass
                            lines = [l.strip() for l in full_body.splitlines() if l.strip()]
                            for l in lines[:4]:
                                if re.fullmatch(r'[A-Za-z0-9]{6,8}', l):
                                    return l
                            m2 = re.search(r'\b([A-Za-z0-9]{6})\b', full_body[:200])
                            if m2:
                                return m2.group(1)
            except Exception as e:
                print("voidash err:", str(e)[:120])
            time.sleep(6)
    return None


async def farm_one(model="Opus"):
    res = {"status": "error", "step": "init", "model": model}
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
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()
        try:
            # ===== 2) signup =====
            await page.goto(NOTION_SIGNUP, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            email_input = page.locator("input[type=email]").first
            await email_input.fill(addr)
            await page.wait_for_timeout(600)
            cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
            if await cont.count():
                await cont.click()
            else:
                await email_input.press("Enter")
            await page.wait_for_timeout(5000)
            body = (await page.inner_text("body")).lower()
            if "invalid email domain" in body or "problem" in body:
                res["error"] = "rejected: " + body[:150]
                await page.screenshot(path=f"{BASE}/err_{int(time.time())}.png")
                return res

            # ===== 3) code =====
            if "verification" in body or "code" in body:
                sent_ts = time.time()
                code = await asyncio.to_thread(voidash_wait_code, key, 240, sent_ts)
                if not code:
                    res["error"] = "otp-not-found"
                    await page.screenshot(path=f"{BASE}/err_{int(time.time())}.png")
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

            # password (если есть)
            body = (await page.inner_text("body")).lower()
            pw_input = page.locator("input[type=password]").first
            if "password" in body and await pw_input.count():
                pw = "Not!" + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                res["password"] = pw
                await pw_input.fill(pw)
                await page.wait_for_timeout(400)
                cont3 = page.get_by_role("button", name=re.compile("Continue|Sign up|Create", re.I)).first
                if await cont3.count():
                    await cont3.click()
                else:
                    await pw_input.press("Enter")
                await page.wait_for_timeout(7000)

            # ===== 4) onboarding =====
            for attempt in range(15):
                body = (await page.inner_text("body")).lower()
                if "customize your profile" in body or "your name" in body:
                    name_inputs = page.locator("input[type=text], input:not([type])")
                    cnt = await name_inputs.count()
                    for j in range(min(cnt, 1)):
                        await name_inputs.nth(j).fill(random.choice(FIRSTS).capitalize() + " " + random.choice(FIRSTS).capitalize())
                    cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
                    if await cont.count():
                        await cont.click()
                        for _ in range(10):
                            await page.wait_for_timeout(1500)
                            b2 = (await page.inner_text("body")).lower()
                            if "customize your profile" not in b2 and "your name" not in b2:
                                break
                    continue
                if "how do you want to use" in body:
                    opt = page.get_by_text(re.compile("for personal|for myself", re.I)).first
                    if await opt.count():
                        await opt.click()
                        await page.wait_for_timeout(2000)
                    cont = page.get_by_role("button", name=re.compile("Continue", re.I)).first
                    if await cont.count():
                        await cont.click()
                    await page.wait_for_timeout(3000)
                    continue
                if "start with your real work" in body or "connect email" in body:
                    btn = page.get_by_role("button", name=re.compile("Start from scratch", re.I)).first
                    if await btn.count():
                        await btn.click()
                        # ждём смены экрана
                        for _ in range(10):
                            await page.wait_for_timeout(1500)
                            b2 = (await page.inner_text("body")).lower()
                            if "start with your real work" not in b2:
                                break
                        continue
                if "create" in body and "workspace" in body:
                    btn = page.get_by_role("button", name=re.compile("Create new workspace", re.I)).first
                    if await btn.count():
                        await btn.click()
                        await page.wait_for_timeout(4000)
                        continue
                if "desktop" in body and ("skip" in body or "faster" in body):
                    skip = page.get_by_role("button", name=re.compile("skip for now|skip", re.I)).first
                    if await skip.count():
                        await skip.click()
                        await page.wait_for_timeout(3000)
                        continue
                if "/onboarding" not in page.url:
                    break
                # generic continue — только кликабельные кнопки без disabled
                cont = page.locator('button:enabled, [role=button]:not([aria-disabled="true"])').filter(has_text=re.compile(r"^\s*(Continue|Next|Get started)\s*$", re.I)).first
                if await cont.count():
                    await cont.click()
                    await page.wait_for_timeout(3000)
                else:
                    break

            res["post_onboarding_url"] = page.url
            print("POST-ONBOARDING:", page.url)

            # ===== 5) model select + test =====
            # Если после онбординга мы уже на /chat — НЕ делаем goto (перезагрузка убивает чат-сессию)
            if "/chat" not in page.url:
                await page.goto("https://app.notion.com/chat", wait_until="domcontentloaded", timeout=60000)
            try:
                await page.locator('[aria-label="Choose AI model"]').first.wait_for(state="visible", timeout=45000)
            except Exception:
                # fallback: перезагрузка + повторное ожидание
                try:
                    await page.goto("https://app.notion.com/chat", wait_until="domcontentloaded", timeout=60000)
                    await page.locator('[aria-label="Choose AI model"]').first.wait_for(state="visible", timeout=45000)
                except Exception:
                    res["error"] = "chat/model button missing"
                    await ctx.storage_state(path=f"{BASE}/state_{addr.replace('@', '_at_').replace('.', '_')}.json")
                    res["state_path"] = f"{BASE}/state_{addr.replace('@', '_at_').replace('.', '_')}.json"
                    res["status"] = "registered-no-chat"
                    await browser.close()
                    return res
            await page.wait_for_timeout(2000)
            await page.locator('[aria-label="Choose AI model"]').first.click()
            await page.wait_for_timeout(2500)
            items = page.locator('[role=menuitem]')
            cnt = await items.count()
            target = None
            for j in range(cnt):
                t = await items.nth(j).inner_text()
                if model.lower() in t.lower():
                    target = items.nth(j)
                    break
            if target is None:
                res["error"] = f"model {model} not in menu"
            else:
                await target.click()
                await page.wait_for_timeout(2000)
                print("MODEL SELECTED:", model)
                # test message
                chat_box = page.locator('[contenteditable=true]').first
                await chat_box.click()
                await chat_box.fill("Hello! Which model are you? Answer in one short sentence.")
                await page.wait_for_timeout(500)
                submit = page.locator('[aria-label="Submit AI message"]').first
                if await submit.count():
                    await submit.click()
                else:
                    await chat_box.press("Enter")
                # wait response
                for i in range(40):
                    await page.wait_for_timeout(2500)
                    body = (await page.inner_text("body")).lower()
                    if "working on your request" not in body and "connecting the details" not in body:
                        if "hello! which model" in body:
                            break
                body_full = await page.inner_text("body")
                # extract reply: текст после нашего промпта
                try:
                    idx = body_full.lower().rfind("hello! which model")
                    reply = body_full[idx + 200:idx + 600].strip()
                    res["ai_reply"] = reply[:300]
                except Exception:
                    pass
                res["model_active"] = model
            res["final_url"] = page.url
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


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--export":
        export_pool()
        return
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    model = sys.argv[2] if len(sys.argv) > 2 else "Opus"
    for i in range(n):
        print(f"=== farm {i+1}/{n} model={model} ===")
        res = await farm_one(model)
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        print("RESULT:", json.dumps(res, ensure_ascii=False)[:700])
        if res.get("status") != "ok" and i + 1 < n:
            print("-> continuing to next account")


if __name__ == "__main__":
    asyncio.run(main())


def export_pool():
    """Конвертирует farm_accounts.jsonl → accounts.json для app/ сервера."""
    accounts = []
    if not os.path.exists(OUT):
        print("farm_accounts.jsonl не найден — сначала запусти ферму")
        return
    with open(OUT, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("status") != "ok":
                continue
            accounts.append({
                "token_v2": rec.get("token_v2") or "",
                "space_id": rec.get("space_id") or "",
                "user_id": rec.get("user_id") or "",
                "space_view_id": rec.get("space_view_id") or "",
                "user_name": rec.get("user_name") or "",
                "user_email": rec.get("email") or "",
            })
    out_path = os.path.join(os.path.dirname(BASE), "accounts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)
    print(f"export: {len(accounts)} аккаунтов -> {out_path}")
