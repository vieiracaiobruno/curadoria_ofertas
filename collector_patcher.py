# collector_patcher.py
# Uso: python collector_patcher.py /caminho/para/collector.py
import sys, re, os, datetime

def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def save(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def remove_method(src, method_name):
    pattern = rf'\n(\s*)def\s+{re.escape(method_name)}\s*\([^\)]*\)\s*:\s*\n(?:(?:\1\s+.*\n)+)'
    return re.sub(pattern, '\n', src)

NEW_METHOD = r"""
    def _resolve_store_info(self, offer_card_html=None, parsed: dict | None = None, product_url: str | None = None) -> dict:
        \"\"\"Resolve informações de loja (store_name, store_id, store_id_alt).\"\"\"
        out = {\"store_name\": None, \"store_id\": None, \"store_id_alt\": None}
        if parsed:
            if parsed.get(\"seller_id\"):
                out[\"store_id\"] = str(parsed[\"seller_id\"])
            if parsed.get(\"seller_id_alt\"):
                out[\"store_id_alt\"] = str(parsed[\"seller_id_alt\"])
            if parsed.get(\"seller_nickname\"):
                out[\"store_name\"] = parsed[\"seller_nickname\"]
            if out[\"store_id\"] or out[\"store_name\"]:
                return out
        if offer_card_html:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(offer_card_html, \"html.parser\")
                a_seller = soup.select_one('[data-testid=\"seller-link\"], a[href*=\"/perfil/\"], a[href*=\"/lojas/ofertas/\"]')
                if a_seller:
                    name = a_seller.get_text(strip=True) or None
                    if name:
                        out[\"store_name\"] = name
                    href = (a_seller.get(\"href\") or \"\").strip()
                    if \"/perfil/\" in href and not out[\"store_id\"]:
                        maybe_id = href.split(\"/perfil/\", 1)[-1].strip(\"/ \")
                        if maybe_id:
                            out[\"store_id\"] = maybe_id
                    if \"/lojas/ofertas/\" in href and not out[\"store_id_alt\"]:
                        maybe_alt = href.split(\"/lojas/ofertas/\", 1)[-1].strip(\"/ \")
                        if maybe_alt:
                            out[\"store_id_alt\"] = maybe_alt
                container = soup.select_one('[data-seller-id], [data-seller-nickname], [data-seller-alt]')
                if container:
                    out[\"store_id\"] = out[\"store_id\"] or container.get(\"data-seller-id\")
                    out[\"store_id_alt\"] = out[\"store_id_alt\"] or container.get(\"data-seller-alt\")
                    out[\"store_name\"] = out[\"store_name\"] or container.get(\"data-seller-nickname\")
                if out[\"store_id\"] or out[\"store_name\"]:
                    return out
            except Exception:
                pass
        if product_url:
            try:
                import requests
                from bs4 import BeautifulSoup
                headers = {\"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; Win64; x64)\"}
                r = requests.get(product_url, timeout=10, headers=headers)
                if r.ok:
                    soup = BeautifulSoup(r.text, \"html.parser\")
                    a_seller = soup.select_one('[data-testid=\"seller-link\"], a[href*=\"/perfil/\"]')
                    if a_seller:
                        text = a_seller.get_text(strip=True)
                        out[\"store_name\"] = out[\"store_name\"] or (text if text else None)
                        href = (a_seller.get(\"href\") or \"\").strip()
                        if \"/perfil/\" in href and not out[\"store_id\"]:
                            out[\"store_id\"] = href.split(\"/perfil/\", 1)[-1].strip(\"/ \")
            except Exception:
                pass
        return out
"""

def inject_new_method(src):
    if "_resolve_store_info(" in src:
        return src
    m = re.search(r'(class\\s+Collector\\b[^\\n]*\\n)', src)
    if m:
        pos = m.end()
        return src[:pos] + NEW_METHOD + src[pos:]
    return src + "\\n\\n" + NEW_METHOD

def inject_enrichment_in_parse(src):
    m = re.search(r'(def\\s+_parse_ml_offers\\s*\\([^\\)]*\\)\\s*:\\s*\\n)', src)
    if not m:
        return src
    start = m.end()
    rest = src[start:]
    m_end = re.search(r'^\\s*def\\s+|^\\s*class\\s+', rest, flags=re.M)
    end = start + (m_end.start() if m_end else len(rest))
    block = src[start:end]
    if "self._resolve_store_info(" in block:
        return src
    new_block = re.sub(
        r'(\\n\\s*items\\.append\\(\\s*parsed\\s*\\)\\s*)',
        '\\n        # === Enriquecer com dados de loja ===\\n'
        '        _store_tmp = self._resolve_store_info(offer_card_html=str(card) if \"card\" in locals() else None,\\n'
        '                                             parsed=parsed,\\n'
        '                                             product_url=parsed.get(\"url\"))\\n'
        '        parsed[\"store_name\"] = _store_tmp.get(\"store_name\")\\n'
        '        parsed[\"store_id\"] = _store_tmp.get(\"store_id\")\\n'
        '        parsed[\"store_id_alt\"] = _store_tmp.get(\"store_id_alt\")\\n'
        r'\\1',
        block,
        count=1
    )
    return src[:start] + new_block + src[end:]

def inject_fallback_in_save(src):
    m = re.search(r'(def\\s+_save_product_and_offer\\s*\\([^\\)]*\\)\\s*:\\s*\\n)', src)
    if not m:
        return src
    start = m.end()
    rest = src[start:]
    m_end = re.search(r'^\\s*def\\s+|^\\s*class\\s+', rest, flags=re.M)
    end = start + (m_end.start() if m_end else len(rest))
    block = src[start:end]
    if "if not (parsed.get(\"store_id\") or parsed.get(\"store_name\"))" in block and "self._resolve_store_info(" in block:
        return src
    first_content = re.search(r'^(\\s+)\\S', block, flags=re.M)
    indent = first_content.group(1) if first_content else "        "
    inject = (
        f"{indent}# Fallback: garantir dados da loja\\n"
        f"{indent}if not (parsed.get(\\\"store_id\\\") or parsed.get(\\\"store_name\\\")):\\n"
        f"{indent}    _store_tmp = self._resolve_store_info(parsed=parsed, product_url=parsed.get(\\\"url\\\"))\\n"
        f"{indent}    parsed[\\\"store_name\\\"] = parsed.get(\\\"store_name\\\") or _store_tmp.get(\\\"store_name\\\")\\n"
        f"{indent}    parsed[\\\"store_id\\\"] = parsed.get(\\\"store_id\\\") or _store_tmp.get(\\\"store_id\\\")\\n"
        f"{indent}    parsed[\\\"store_id_alt\\\"] = parsed.get(\\\"store_id_alt\\\") or _store_tmp.get(\\\"store_id_alt\\\")\\n\\n"
    )
    new_block = inject + block
    return src[:start] + new_block + src[end:]

def main():
    if len(sys.argv) != 2:
        print("Uso: python collector_patcher.py /caminho/para/collector.py")
        sys.exit(2)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Arquivo não encontrado: {path}")
        sys.exit(1)
    src = load(path)
    backup_path = path + ".backup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(src)

    # Remover métodos antigos
    src = remove_method(src, "_find_seller_link_and_name")
    src = remove_method(src, "_resolve_store_by_alt_or_scrape")

    # Injetar novo método e integrações
    src = inject_new_method(src)
    src = inject_enrichment_in_parse(src)
    src = inject_fallback_in_save(src)

    save(path, src)
    print("OK: Patch aplicado em", path)
    print("Backup criado em", backup_path)

if __name__ == "__main__":
    main()
