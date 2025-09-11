import requests
from bs4 import BeautifulSoup
import io
import sys
import re
from urllib.parse import unquote, urlparse, parse_qs

# ---------- Função utilitária ----------
def extrair_codigo(url: str) -> str | None:
    """
    Extrai o código MLB de diferentes tipos de URLs do Mercado Livre:
      1) produto.mercadolivre.com.br/MLB-##########
      2) click1.mercadolivre.com.br com parâmetro ?url=...
      3) mercadolivre.com.br/.../p/MLB##########
    """
    if not url:
        return None

    # Padrões aceitos
    padroes = [
        r"MLB-\d{10}",   # caso 1 → MLB-##########
        r"MLB\d{8,}"     # caso 3 → MLB##########
    ]

    # Caso seja um link de redirecionamento (click1)
    if "click1.mercadolivre.com.br" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        destino = qs.get("url", [None])[0]
        if destino:
            url_produto = unquote(destino)
            for p in padroes:
                m = re.search(p, url_produto)
                if m:
                    return m.group()

    # Caso direto (produto ou catálogo)
    for p in padroes:
        m = re.search(p, url)
        if m:
            return m.group()

    return None


# ---------- Config HTTP ----------
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    )
}

base = "https://www.mercadolivre.com.br/ofertas?page="
start = 1

# Redireciona saída para buffer
buffer = io.StringIO()
sys.stdout = buffer

while True:
    url_final = f"{base}{start}"
    try:
        r = requests.get(url_final, headers=headers, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Falha ao acessar {url_final}: {e}")
        break

    site = BeautifulSoup(r.content, "html.parser")

    descricoes = site.find_all("h3", class_="poly-component__title-wrapper")
    precosAntes = site.find_all("s", class_="andes-money-amount andes-money-amount--previous andes-money-amount--cents-comma")
    precosDepois = site.find_all("span", class_="andes-money-amount andes-money-amount--cents-superscript")
    links = site.find_all("a", class_="poly-component__title")
    descontos = site.find_all("span", class_="andes-money-amount__discount")

    if not descricoes or not links:
        print("Acabou")
        break

    for descricao, precoAntes, precoDepois, link, desconto in zip(descricoes, precosAntes, precosDepois, links, descontos):
        href = link.get("href", "")

        print("Produto: " + (descricao.get_text(strip=True) or ""))
        print("Valor Anterior: " + (precoAntes.get_text(strip=True) if precoAntes else ""))
        print("Valor Depois: " + (precoDepois.get_text(strip=True) if precoDepois else ""))
        print("Desconto: " + (desconto.get_text(strip=True) if desconto else ""))

        codigo = extrair_codigo(href) or "N/A"
        print("MLB: " + codigo)
        print(f"Link: {href}\n")

    start += 1
    if start > 1:  # Limita a 5 páginas
        break

# Restaura stdout e grava arquivo
sys.stdout = sys.__stdout__
with open("saida.txt", "w", encoding="utf-8") as f:
    f.write(buffer.getvalue())
