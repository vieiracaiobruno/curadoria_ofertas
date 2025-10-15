# Guia de Uso: Alternância entre Selenium e HTTP Direto

## Visão Geral

O sistema agora suporta dois modos de coleta de dados do Mercado Livre:

1. **Modo Selenium** (padrão): Usa o navegador Chrome via Selenium para coletar dados
2. **Modo HTTP Direto**: Faz requisições HTTP diretas sem usar Selenium

## Configuração

### Via Configuração do Sistema

Adicione a variável `USE_SELENIUM` no banco de dados de configurações ou no arquivo `.env`:

```
USE_SELENIUM=true   # Usa Selenium (padrão)
USE_SELENIUM=false  # Usa HTTP direto
```

Valores aceitos para ativar Selenium: `true`, `1`, `yes`, `sim`

### Via Código

```python
from backend.modules.collectors.ml_collector import MLCollector

# Modo Selenium (padrão)
collector = MLCollector()
# ou
collector = MLCollector(use_selenium=True)

# Modo HTTP direto
collector = MLCollector(use_selenium=False)
```

## Diferenças entre os Modos

### Modo Selenium (use_selenium=True)

**Vantagens:**
- Acesso completo a todos os dados disponíveis na página
- Suporta JavaScript e conteúdo dinâmico
- Pode gerar links de afiliado curtos
- Pode extrair ganho_real

**Desvantagens:**
- Mais lento
- Requer Chrome instalado
- Consome mais recursos (memória e CPU)
- Pode ser bloqueado por anti-bot

**Campos extraídos:**
- ✅ store_name
- ✅ seller_id
- ✅ id_product
- ✅ preco_original
- ✅ preco_oferta
- ✅ desconto
- ✅ nome_produto
- ✅ imagem_url
- ✅ seller_score (do HTML via termômetro)
- ✅ ganho_real
- ✅ url_afiliado_curta

### Modo HTTP Direto (use_selenium=False)

**Vantagens:**
- Mais rápido
- Não requer Chrome instalado
- Consome menos recursos
- Mais difícil de ser detectado

**Desvantagens:**
- Não pode gerar links de afiliado curtos
- Não pode extrair ganho_real (requer interação)
- seller_score vem do JSON (reputation_level)

**Campos extraídos:**
- ✅ store_name
- ✅ seller_id
- ✅ id_product
- ✅ preco_original
- ✅ preco_oferta
- ✅ desconto
- ✅ nome_produto
- ✅ imagem_url
- ✅ seller_score (do JSON via reputation_level: "5_green" → 5)
- ❌ ganho_real (definido como None)
- ❌ url_afiliado_curta (definido como None)

## Funcionamento do Modo HTTP

### 1. Coleta de Páginas de Ofertas

```
URL: https://www.mercadolivre.com.br/ofertas?page={page_num}
Headers:
  - accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8
  - accept-language: pt-BR,pt;q=0.9,en;q=0.8
  - cache-control: max-age=0
  - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
```

### 2. Extração de Links de Produtos

Os links são extraídos usando BeautifulSoup da mesma forma que no modo Selenium:
- Busca por elementos `<a>` com classe `poly-component__title`
- Extrai o atributo `href`

### 3. Coleta de Dados de Produtos

```
URL: https://www.mercadolivre.com.br/p/{MLB_ID}
Headers: (mesmos da listagem)
Cookies: cookies básicos do Mercado Livre
```

### 4. Extração do seller_score

No modo HTTP, o `seller_score` é extraído do campo `reputation_level` no JSON `__PRELOADED_STATE__`:

```json
{
  "pageState": {
    "initialState": {
      "components": {
        "track": {
          "melidata_event": {
            "event_data": {
              "reputation_level": "5_green"
            }
          }
        }
      }
    }
  }
}
```

**Formato:** `"<numero>_<cor>"`
- Exemplos: `"5_green"`, `"4_yellow"`, `"3_red"`, `"2_orange"`, `"1_lightred"`
- **Extração:** Apenas o primeiro número antes do underscore
  - `"5_green"` → `5`
  - `"4_yellow"` → `4`
  - `"3_red"` → `3`

## Exemplos de Uso

### Exemplo 1: Pipeline Padrão

```python
from backend.modules.collectors.ml_collector import MLCollector

# Usa configuração do sistema (USE_SELENIUM)
collector = MLCollector()
items = collector.run_collection()
collector.close()
```

### Exemplo 2: Teste Rápido sem Selenium

```python
from backend.modules.collectors.ml_collector import MLCollector

# Força modo HTTP para teste rápido
collector = MLCollector(use_selenium=False)
items = collector.run_collection()
print(f"Coletados {len(items)} itens")

for item in items[:5]:  # Mostra primeiros 5
    print(f"- {item['nome_produto']} - Score: {item['seller_score']}")

collector.close()
```

### Exemplo 3: Comparação de Modos

```python
import time
from backend.modules.collectors.ml_collector import MLCollector

# Modo Selenium
start = time.time()
collector_sel = MLCollector(use_selenium=True)
items_sel = collector_sel.run_collection()
time_sel = time.time() - start
collector_sel.close()

# Modo HTTP
start = time.time()
collector_http = MLCollector(use_selenium=False)
items_http = collector_http.run_collection()
time_http = time.time() - start
collector_http.close()

print(f"Selenium: {len(items_sel)} itens em {time_sel:.2f}s")
print(f"HTTP: {len(items_http)} itens em {time_http:.2f}s")
print(f"Ganho de velocidade: {(time_sel/time_http):.2f}x")
```

## Migração de Código Existente

O código existente **não precisa ser alterado**. O modo Selenium é o padrão, garantindo compatibilidade com o comportamento anterior.

Para habilitar o modo HTTP:
1. Adicione `USE_SELENIUM=false` na configuração
2. Ou passe `use_selenium=False` ao criar o MLCollector

## Troubleshooting

### Problema: "ModuleNotFoundError: No module named 'requests'"

**Solução:** Instale as dependências:
```bash
pip install -r requirements.txt
```

### Problema: seller_score retorna None no modo HTTP

**Causa:** O campo `reputation_level` não existe no JSON ou está em formato inesperado.

**Solução:** Verifique se o produto tem avaliação de vendedor no Mercado Livre.

### Problema: HTTP retorna bloqueio (403, 429)

**Solução:** 
1. Aumente o delay entre requisições: `ML_REQUEST_DELAY_SEC=3`
2. Use modo Selenium temporariamente
3. Aguarde alguns minutos antes de tentar novamente

## Considerações de Desempenho

| Aspecto | Selenium | HTTP Direto |
|---------|----------|-------------|
| Velocidade | 🐌 Lento | 🚀 Rápido |
| Recursos | 💾 Alto | 💾 Baixo |
| Detecção | 🚨 Fácil | ✅ Difícil |
| Dados completos | ✅ Sim | ⚠️ Parcial |

**Recomendação:**
- Use **HTTP** para coleta rápida de dados básicos
- Use **Selenium** quando precisar de dados completos (ganho_real, url_afiliado_curta)
