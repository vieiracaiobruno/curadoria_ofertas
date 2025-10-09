import os, re, time, json, random, hashlib, pickle, contextlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime as _dt

import httpx

COOKIE_STORE = Path("backend/http/cookies_store.pkl")

ANTI_BOT_PATTERNS = [
    r"enable javascript",
    r"unusual traffic",
    r"cloudflare",
    r"access denied",
    r"temporarily unavailable",
    r"captcha",
]

UA_POOL = [
    # Chrome (Win)
    ("Windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    # Chrome (macOS)
    ("macOS", "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    # Firefox
    ("Windows", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"),
    # Safari
    ("macOS", "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.4 Safari/605.1.15"),
]

def _rand_accept_language() -> str:
    options = [
        "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "pt-BR,pt;q=0.8,en;q=0.6",
        "pt-BR,pt;q=0.9,en;q=0.6",
    ]
    return random.choice(options)

def _should_use_compressed() -> bool:
    return random.random() < 0.15  # 15% das vezes

def _build_headers(ua: str, platform: str, referer: Optional[str]) -> Dict[str, str]:
    accept_enc = "gzip, deflate" if _should_use_compressed() else "identity"
    sec_ch_ua_platform = '"Windows"' if platform == "Windows" else '"macOS"'
    headers = {
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Accept-Language": _rand_accept_language(),
        "Accept-Encoding": accept_enc,
        "DNT": str(random.choice([0, 1])),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-CH-UA-Platform": sec_ch_ua_platform,
    }
    # Opcional: client hints mínimos
    headers["Sec-CH-UA"] = '"Chromium";v="124", "Not:A-Brand";v="99"'
    headers["Sec-CH-UA-Mobile"] = "?0"
    if referer:
        headers["Referer"] = referer
    return headers

def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]

def _load_cookies() -> httpx.Cookies:
    if COOKIE_STORE.exists():
        try:
            with COOKIE_STORE.open("rb") as fp:
                jar_dict = pickle.load(fp)
            cookies = httpx.Cookies()
            for k, v in jar_dict.items():
                cookies.set(k, v)
            return cookies
        except Exception:
            return httpx.Cookies()
    return httpx.Cookies()

def _save_cookies(cookies: httpx.Cookies):
    try:
        jar_dict = {c[0]: c[1] for c in cookies.jar}
        with COOKIE_STORE.open("wb") as fp:
            pickle.dump(jar_dict, fp)
    except Exception:
        pass

def _looks_like_challenge(status: int, text: str, content_type: str) -> bool:
    if status in (403, 429, 503):
        return True
    if "text/html" not in content_type.lower():
        return True
    snippet = text[:500].lower()
    for pat in ANTI_BOT_PATTERNS:
        if re.search(pat, snippet):
            return True
    # Página muito curta
    if len(text) < 400 and "<html" in text.lower():
        return True
    return False

class BrowserLikeClient:
    """
    Níveis:
      1 - httpx (light)
      2 - httpx (light) + retry com re-geração headers
      3 - fallback headless (Playwright) se disponível
    """
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ua_platform, self.ua = random.choice(UA_POOL)
        self.cookies = _load_cookies()
        self.last_referer: Optional[str] = None
        self.metrics = {
            "requests": 0,
            "escalations": 0,
            "playwright_used": 0,
            "challenges": 0,
            "success": 0,
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=15.0,
            http2=True,
            headers=_build_headers(self.ua, self.ua_platform, self.last_referer),
            cookies=self.cookies,
            follow_redirects=True,
        )

    def warmup(self):
        try:
            with self._client() as c:
                c.get(self.base_url, timeout=10)
        except Exception:
            pass

    def _save_snapshot(self, url: str, html: str, stage: str):
        """
        Salva HTML em logs/ snapshot_<timestamp>_<stage>_<sanitized>.txt
        """
        try:
            if not html:
                return
            os.makedirs("logs", exist_ok=True)
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (url.split("?")[0])[-60:])
            fname = f"logs/snapshot_{_dt.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{stage}_{safe_name}.txt"
            with open(fname, "w", encoding="utf-8") as fp:
                fp.write("URL: " + url + "\n")
                fp.write("STAGE: " + stage + "\n\n")
                fp.write(html)
            print(f"[browser_client] Snapshot salvo: {fname}")
        except Exception as e:
            print(f"[browser_client] Falha ao salvar snapshot: {e}")

    def fetch(self, url: str, escalate: bool = True) -> Tuple[str, Dict[str, Any]]:
        """
        Retorna (html, meta)
        meta: dict com status, client_level, escalated, challenge_detected
        """
        meta = {
            "status": None,
            "client_level": 1,
            "escalated": False,
            "challenge_detected": False,
            "url_hash": _hash_url(url),
        }
        delay = random.uniform(0.4, 1.8)
        time.sleep(delay)
        # Nível 1
        self._current_stage = "lvl1"
        html, status, ctype = self._try_request(url)
        meta["status"] = status
        if html is not None and not _looks_like_challenge(status, html, ctype):
            self.last_referer = url
            self.metrics["success"] += 1
            _save_cookies(self.cookies)
            return html, meta

        meta["challenge_detected"] = True
        self.metrics["challenges"] += 1
        if not escalate:
            return (html or ""), meta

        # Nível 2 (regenera UA e headers)
        self.metrics["escalations"] += 1
        meta["escalated"] = True
        old_ua = self.ua
        self.ua_platform, self.ua = random.choice(UA_POOL)
        self._current_stage = "lvl2"
        html2, status2, ctype2 = self._try_request(url)
        meta["status"] = status2
        meta["client_level"] = 2
        if html2 is not None and not _looks_like_challenge(status2, html2, ctype2):
            self.last_referer = url
            self.metrics["success"] += 1
            _save_cookies(self.cookies)
            return html2, meta

        # Nível 3 (Playwright) – opcional
        self._current_stage = "playwright"
        html3 = self._playwright_fetch(url)
        meta["client_level"] = 3
        if html3:
            self.metrics["playwright_used"] += 1
            self.metrics["success"] += 1
            self.last_referer = url
            _save_cookies(self.cookies)
            return html3, meta

        return (html2 or html or ""), meta

    def _try_request(self, url: str):
        self.metrics["requests"] += 1
        with self._client() as c:
            try:
                r = c.get(url)
                content_type = r.headers.get("Content-Type", "")
                # salva snapshot (nivel pode ser 1 ou 2, definido fora via self._current_stage)
                stage = getattr(self, "_current_stage", "lvl?")
                self._save_snapshot(url, r.text, stage)
                return r.text, r.status_code, content_type
            except Exception:
                return None, 0, ""

    def _playwright_fetch(self, url: str) -> Optional[str]:
        # Só tenta se playwright instalado
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=self.ua,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                )
                page = context.new_page()
                page.goto(self.base_url, wait_until="load")
                time.sleep(random.uniform(0.8, 1.5))
                page.goto(url, wait_until="networkidle", timeout=25000)
                html = page.content()
                self._save_snapshot(url, html, "playwright")
                context.storage_state(path="backend/http/playwright_state.json")
                browser.close()
                # CAPTCHA heurística
                if re.search(r"captcha", html[:1000], re.IGNORECASE):
                    return None
                return html
        except Exception:
            return None