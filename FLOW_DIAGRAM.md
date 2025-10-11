# Diagrama de Fluxo: Selenium vs HTTP

## Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────┐
│                      MLCollector                             │
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │         __init__(use_selenium)                    │      │
│  │                                                    │      │
│  │  ┌───────────────┐          ┌─────────────────┐  │      │
│  │  │ USE_SELENIUM? │──Yes───▶ │ Init Selenium   │  │      │
│  │  └───────┬───────┘          └─────────────────┘  │      │
│  │          │                                         │      │
│  │          No                                        │      │
│  │          ▼                                         │      │
│  │  ┌─────────────────┐                              │      │
│  │  │ Init HTTP Mode  │                              │      │
│  │  │ - Set headers   │                              │      │
│  │  │ - Set cookies   │                              │      │
│  │  └─────────────────┘                              │      │
│  └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Fluxo de Coleta: Modo Selenium (use_selenium=True)

```
                   run_collection()
                          │
                          ▼
          ┌───────────────────────────────┐
          │ Para cada página (1 to max)   │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────────┐
          │ _fetch_ml_ofertas_page(page)      │
          │                                    │
          │ ┌──────────────────────────────┐  │
          │ │ selenium_listing.get_page()  │  │
          │ │ ↓ Chrome via Selenium        │  │
          │ │ ↓ Wait for elements          │  │
          │ │ ↓ Return page_source (HTML)  │  │
          │ └──────────────────────────────┘  │
          └───────────────┬───────────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │ _parse_ml_offers(html)        │
          │ ↓ BeautifulSoup               │
          │ ↓ Find <a class="poly-...">   │
          │ ↓ Extract href (product URLs) │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────────────┐
          │ _enrich_parallel(offers)              │
          │                                        │
          │ ┌────────────────────────────────┐    │
          │ │ For each offer in parallel:    │    │
          │ │                                │    │
          │ │ _enrich_with_client():         │    │
          │ │ ↓ selenium.get_page(url)       │    │
          │ │ ↓ Extract __PRELOADED_STATE__  │    │
          │ │ ↓ seller_score (HTML termôm.)  │    │
          │ │ ↓ ganho_real (HTML)            │    │
          │ │ ↓ url_afiliado_curta (click)   │    │
          │ └────────────────────────────────┘    │
          └───────────────┬───────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ Return items  │
                  │ (all fields)  │
                  └───────────────┘
```

## Fluxo de Coleta: Modo HTTP (use_selenium=False)

```
                   run_collection()
                          │
                          ▼
          ┌───────────────────────────────┐
          │ Para cada página (1 to max)   │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────────────┐
          │ _fetch_ml_ofertas_page(page)          │
          │   ↓ check: use_selenium == False      │
          │   ↓ calls _fetch_ml_ofertas_page_http │
          └───────────────┬───────────────────────┘
                          │
                          ▼
          ┌───────────────────────────────────────┐
          │ _fetch_ml_ofertas_page_http(page)     │
          │                                        │
          │ ┌────────────────────────────────┐    │
          │ │ requests.get(url, headers)     │    │
          │ │ ↓ Direct HTTP call             │    │
          │ │ ↓ No browser                   │    │
          │ │ ↓ Return response.text (HTML)  │    │
          │ └────────────────────────────────┘    │
          └───────────────┬───────────────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │ _parse_ml_offers(html)        │
          │ ↓ Same as Selenium mode       │
          │ ↓ BeautifulSoup               │
          │ ↓ Extract product URLs        │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────────────┐
          │ _enrich_parallel(offers)              │
          │   ↓ check: use_selenium == False      │
          │   ↓ calls _enrich_with_http           │
          └───────────────┬───────────────────────┘
                          │
                          ▼
          ┌───────────────────────────────────────┐
          │ _enrich_with_http(item)               │
          │                                        │
          │ ┌────────────────────────────────┐    │
          │ │ requests.get(url, headers)     │    │
          │ │ ↓ Direct HTTP call             │    │
          │ │ ↓ Parse HTML with BS4          │    │
          │ │ ↓ Extract __PRELOADED_STATE__  │    │
          │ │ ↓ seller_score (JSON field)    │    │
          │ │ ↓ ganho_real = None            │    │
          │ │ ↓ url_afiliado_curta = None    │    │
          │ └────────────────────────────────┘    │
          └───────────────┬───────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ Return items  │
                  │ (partial)     │
                  └───────────────┘
```

## Comparação: Extração do seller_score

### Modo Selenium
```
HTML da página
    │
    ▼
┌─────────────────────────────────────────┐
│ <ul class="ui-seller-data-status__      │
│      thermometer thermometer-large"     │
│     value="5">                          │
│   <li>...</li>                          │
│ </ul>                                   │
└───────────────┬─────────────────────────┘
                │
                ▼
    _extract_seller_score(soup)
                │
                ▼
    Busca elemento <ul> com classes:
    - ui-seller-data-status__thermometer
    - thermometer-large
                │
                ▼
    Extrai atributo value="5"
                │
                ▼
        seller_score = 5
```

### Modo HTTP
```
JSON __PRELOADED_STATE__
    │
    ▼
┌─────────────────────────────────────────┐
│ {                                       │
│   "pageState": {                        │
│     "initialState": {                   │
│       "components": {                   │
│         "track": {                      │
│           "melidata_event": {           │
│             "event_data": {             │
│               "reputation_level":       │
│                 "5_green"               │
│             }                           │
│           }                             │
│         }                               │
│       }                                 │
│     }                                   │
│   }                                     │
│ }                                       │
└───────────────┬─────────────────────────┘
                │
                ▼
    _extract_seller_score_from_json(data)
                │
                ▼
    Navega até reputation_level
                │
                ▼
    Valor: "5_green"
                │
                ▼
    Split por "_" → ["5", "green"]
                │
                ▼
    Pega primeiro elemento → "5"
                │
                ▼
    Converte para int → 5
                │
                ▼
        seller_score = 5
```

## Decisão de Modo

```
┌─────────────────────────────────────────┐
│ MLCollector.__init__(use_selenium=?)    │
└───────────────┬─────────────────────────┘
                │
                ▼
        ┌───────────────┐
        │ use_selenium  │
        │   is None?    │
        └───────┬───────┘
                │
        ┌───────┴───────┐
       Yes              No
        │                │
        ▼                ▼
┌──────────────┐   ┌──────────────┐
│ Read config  │   │ Use explicit │
│ USE_SELENIUM │   │    value     │
└──────┬───────┘   └──────┬───────┘
       │                  │
       ▼                  │
┌──────────────┐          │
│ Parse value  │          │
│ "true"? →True│          │
│ "false"?→Fls │          │
│ "1"? → True  │          │
│ "0"? → False │          │
└──────┬───────┘          │
       │                  │
       └────────┬─────────┘
                │
                ▼
        ┌───────────────┐
        │ self.use_     │
        │  selenium =   │
        │  True/False   │
        └───────┬───────┘
                │
        ┌───────┴────────┐
       True            False
        │                │
        ▼                ▼
┌────────────────┐  ┌────────────────┐
│ Init Selenium  │  │ Init HTTP      │
│ - profile      │  │ - headers      │
│ - listing      │  │ - cookies      │
└────────────────┘  └────────────────┘
```

## Exemplo de Configuração

### Arquivo .env ou config database
```bash
# Selenium mode (padrão)
USE_SELENIUM=true
ML_MAX_PAGES=3
ML_REQUEST_DELAY_SEC=2

# HTTP mode
USE_SELENIUM=false
ML_MAX_PAGES=5
ML_REQUEST_DELAY_SEC=1
```

### Código Python
```python
# Automático (usa config)
collector = MLCollector()

# Forçar Selenium
collector = MLCollector(use_selenium=True)

# Forçar HTTP
collector = MLCollector(use_selenium=False)
```

## Campos Extraídos: Comparação

```
┌─────────────────────┬──────────┬──────────┐
│       Campo         │ Selenium │   HTTP   │
├─────────────────────┼──────────┼──────────┤
│ store_name          │    ✅    │    ✅    │
│ seller_id           │    ✅    │    ✅    │
│ id_product          │    ✅    │    ✅    │
│ preco_original      │    ✅    │    ✅    │
│ preco_oferta        │    ✅    │    ✅    │
│ desconto            │    ✅    │    ✅    │
│ nome_produto        │    ✅    │    ✅    │
│ imagem_url          │    ✅    │    ✅    │
│ seller_score        │ ✅ (HTML)│ ✅ (JSON)│
│ ganho_real          │    ✅    │    ❌    │
│ url_afiliado_curta  │    ✅    │    ❌    │
└─────────────────────┴──────────┴──────────┘

Legenda:
✅ = Extraído
❌ = None (conforme requisito)
```

## Performance Esperada

```
┌────────────────────────────────────────────────┐
│                                                │
│  Selenium Mode                                 │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  100%         │
│  ⏱️  ~15 segundos por produto                  │
│  💾 ~500MB RAM                                 │
│                                                │
│  HTTP Mode                                     │
│  ━━━━━━  20%                                   │
│  ⏱️  ~3 segundos por produto                   │
│  💾 ~50MB RAM                                  │
│                                                │
│  Ganho: 5x mais rápido, 10x menos memória      │
└────────────────────────────────────────────────┘
```

## Casos de Uso Recomendados

### Use Selenium Quando:
- ✅ Precisa de url_afiliado_curta
- ✅ Precisa de ganho_real
- ✅ Não há restrição de tempo/recursos
- ✅ Coleta pequena (poucos produtos)

### Use HTTP Quando:
- ✅ Coleta rápida e em massa
- ✅ Recursos limitados (memória, CPU)
- ✅ Não precisa de todos os campos
- ✅ Quer evitar detecção como bot
- ✅ Chrome não está disponível
