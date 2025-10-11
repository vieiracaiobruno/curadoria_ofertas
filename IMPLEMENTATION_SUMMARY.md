# Implementação: Fluxo Alternativo ao Selenium

## ✅ Implementação Completa

Este documento resume as alterações feitas para implementar o fluxo alternativo ao Selenium, conforme solicitado na issue.

## Arquivos Modificados

### 1. `requirements.txt`
- Adicionado `httpx==0.25.1` (necessário para browser_client.py que já o usava)

### 2. `backend/modules/collectors/ml_collector.py` 
**Principais mudanças:**

#### a) Imports
```python
import requests  # Adicionado para requisições HTTP
```

#### b) Método `__init__`
- Novo parâmetro: `use_selenium: Optional[bool] = None`
- Lógica de seleção de modo:
  ```python
  if use_selenium is None:
      use_selenium_str = get_config("USE_SELENIUM", "true")
      self.use_selenium = use_selenium_str.lower() in ("true", "1", "yes", "sim")
  else:
      self.use_selenium = use_selenium
  ```
- Inicialização condicional do Selenium
- No modo HTTP, configura headers e cookies

#### c) Novos Métodos

**`_extract_seller_score_from_json(data)`**
- Extrai seller_score do campo `reputation_level` no JSON
- Formato: `"5_green"` → `5`
- Implementa o requisito: "o seller_score vai ser recuperado pelo campo reputation_level"
- Lógica: pega apenas o primeiro número antes do underscore

**`_fetch_ml_ofertas_page_http(page_num)`**
- Busca páginas de ofertas via HTTP direto
- URL: `https://www.mercadolivre.com.br/ofertas?page={page_num}`
- Headers conforme especificado no curl da issue
- Retorna HTML da página

**`_enrich_with_http(item)`**
- Enriquece dados do produto via HTTP direto
- URL: produto MLB do item
- Headers conforme especificado no curl da issue
- Extrai dados do `__PRELOADED_STATE__`
- **Diferença 1**: `url_afiliado_curta = None` (não recuperado)
- **Diferença 2**: `ganho_real = None` (não recuperado)
- **Diferença 3**: `seller_score` do JSON via `_extract_seller_score_from_json()`

#### d) Métodos Modificados

**`_fetch_ml_ofertas_page(page_num)`**
- Agora verifica `self.use_selenium`
- Se False, chama `_fetch_ml_ofertas_page_http()`
- Se True, mantém comportamento original (Selenium)

**`_enrich_parallel(offers)`**
- No modo HTTP: chama `_enrich_with_http()` para cada item
- No modo Selenium: mantém comportamento original

**`close()`**
- Só fecha Selenium se `self.use_selenium == True`

**`run_collection()`**
- Adicionado log indicando o modo: "Selenium" ou "HTTP direto (sem Selenium)"

### 3. `SELENIUM_TOGGLE_GUIDE.md` (Novo)
Documentação completa incluindo:
- Visão geral dos dois modos
- Instruções de configuração
- Comparação de recursos
- Explicação do funcionamento HTTP
- Exemplos de uso
- Guia de troubleshooting

## Conformidade com os Requisitos

### ✅ Requisito: Parâmetro de Liga/Desliga
**Implementado:** `USE_SELENIUM` (config) ou `use_selenium` (parâmetro)
- Default: True (mantém comportamento existente)
- Valores aceitos: true/false, 1/0, yes/no, sim/não

### ✅ Requisito: Modo Selenium Ligado
**Implementado:** Quando `use_selenium=True`, o fluxo continua idêntico ao atual

### ✅ Requisito: Chamadas Diretas sem Selenium
**Implementado:** Quando `use_selenium=False`:
- Usa `requests.get()` com headers especificados
- URL ofertas: `https://www.mercadolivre.com.br/ofertas?page={page}`
- Headers: accept, accept-language, cache-control, user-agent (conforme curl)

### ✅ Requisito: Coleta de Links
**Implementado:** 
- Extração via BeautifulSoup (método `_parse_ml_offers` reutilizado)
- Mantém padrão de paginação e max_pages

### ✅ Requisito: Chamada de Produtos
**Implementado:**
- URL: `https://www.mercadolivre.com.br/p/{MLB_ID}`
- Headers: conforme curl especificado
- Cookies básicos incluídos

### ✅ Diferença 1: url_afiliado_curta
**Implementado:** `item["url_afiliado_curta"] = None` no modo HTTP

### ✅ Diferença 2: ganho_real
**Implementado:** `item["ganho_real"] = None` no modo HTTP

### ✅ Diferença 3: seller_score
**Implementado:** 
- Novo método `_extract_seller_score_from_json()`
- Extrai de `reputation_level`
- Formato: `"5_green"` → extrai `5`
- Ignora parte após underscore (`"_green"`, `"_yellow"`, etc.)

## Dados Extraídos por Modo

### Modo Selenium (use_selenium=True)
| Campo | Status |
|-------|--------|
| store_name | ✅ Extraído |
| seller_id | ✅ Extraído |
| id_product | ✅ Extraído |
| preco_original | ✅ Extraído |
| preco_oferta | ✅ Extraído |
| desconto | ✅ Extraído |
| nome_produto | ✅ Extraído |
| imagem_url | ✅ Extraído |
| seller_score | ✅ Do HTML (termômetro) |
| ganho_real | ✅ Extraído |
| url_afiliado_curta | ✅ Gerado |

### Modo HTTP (use_selenium=False)
| Campo | Status |
|-------|--------|
| store_name | ✅ Extraído do JSON |
| seller_id | ✅ Extraído do JSON |
| id_product | ✅ Extraído do JSON |
| preco_original | ✅ Extraído do JSON |
| preco_oferta | ✅ Extraído do JSON |
| desconto | ✅ Extraído do JSON |
| nome_produto | ✅ Extraído do JSON |
| imagem_url | ✅ Extraído do JSON |
| seller_score | ✅ Do JSON (reputation_level) |
| ganho_real | ❌ None (conforme requisito) |
| url_afiliado_curta | ❌ None (conforme requisito) |

## Como Usar

### Opção 1: Via Configuração Global
```bash
# No banco de dados ou .env
USE_SELENIUM=false
```

### Opção 2: Via Código
```python
# HTTP direto
collector = MLCollector(use_selenium=False)
items = collector.run_collection()

# Selenium (padrão)
collector = MLCollector(use_selenium=True)
items = collector.run_collection()
```

## Testes Realizados

### ✅ Teste 1: Verificação de Sintaxe
```bash
python3 -m py_compile backend/modules/collectors/ml_collector.py
# Resultado: ✓ Syntax check passed
```

### ✅ Teste 2: Extração de seller_score
Testado método `_extract_seller_score_from_json()` com 7 casos:
- "5_green" → 5 ✅
- "4_yellow" → 4 ✅
- "3_red" → 3 ✅
- "2_orange" → 2 ✅
- "1_lightred" → 1 ✅
- None data → None ✅
- Missing field → None ✅

**Resultado:** 7/7 testes passaram

### ✅ Teste 3: Estrutura de Código
Verificado que todos os métodos existem:
- `_extract_seller_score_from_json` ✅
- `_fetch_ml_ofertas_page_http` ✅
- `_enrich_with_http` ✅
- Modificações em `_enrich_parallel` ✅
- Modificações em `close` ✅
- Modificações em `run_collection` ✅

## Estatísticas das Mudanças

```
3 arquivos alterados
381 linhas adicionadas
12 linhas removidas
```

Detalhamento:
- `SELENIUM_TOGGLE_GUIDE.md`: +243 linhas (novo arquivo de documentação)
- `backend/modules/collectors/ml_collector.py`: +135 linhas, -12 linhas
- `requirements.txt`: +1 linha

## Compatibilidade

✅ **Retrocompatível:** Código existente continua funcionando sem alterações
- Default é `use_selenium=True`
- Comportamento Selenium não foi modificado
- Novos recursos são opt-in

## Próximos Passos Sugeridos

1. **Teste em Produção:**
   - Teste com `USE_SELENIUM=false` em ambiente de desenvolvimento
   - Compare resultados com modo Selenium
   - Monitore performance e taxa de sucesso

2. **Otimizações Futuras:**
   - Paralelizar requisições HTTP (_enrich_with_http)
   - Adicionar retry automático com backoff
   - Implementar rate limiting configurável
   - Cache de cookies/session mais sofisticado

3. **Monitoramento:**
   - Adicionar métricas de sucesso/falha por modo
   - Logs de tempo de execução
   - Alertas para bloqueios HTTP

## Conclusão

✅ **Todos os requisitos da issue foram implementados:**
- Parâmetro de liga/desliga
- Modo Selenium preservado
- Modo HTTP implementado com curl equivalente
- Três diferenças de extração implementadas corretamente
- Documentação completa
- Testes de validação realizados

A implementação está pronta para uso e é retrocompatível com o código existente.
