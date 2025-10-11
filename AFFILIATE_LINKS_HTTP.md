# Recuperação de Links de Afiliado via HTTP (sem Selenium)

## Visão Geral

Esta funcionalidade permite recuperar links de afiliado curtos do Mercado Livre usando requisições HTTP diretas à API de afiliados, ao invés de usar Selenium para clicar no botão "Compartilhar" na página do produto.

## Vantagens

- ⚡ **Mais rápido**: Busca em lote (batch) ao invés de individual
- 🔧 **Menos recursos**: Não precisa abrir múltiplas janelas do navegador
- 🎯 **Mais eficiente**: Uma única chamada de API para múltiplos produtos
- 🛡️ **Mais robusto**: Menos sujeito a mudanças no layout da página

## Como Funciona

### 1. Atualização de Cookies

Antes de fazer chamadas à API de afiliados, é necessário ter cookies válidos de uma sessão logada.

```python
from backend.modules.collectors.ml_collector import update_all_site_cookies

# Atualiza cookies de todos os sites de coleta
cookies = update_all_site_cookies(
    user_data_dir="/path/to/chrome/profile",
    profile_dir="Profile 1"
)

# Retorna: {'https://www.mercadolivre.com.br': {'cookies': [...], 'localStorage': {...}}}
```

A função `update_all_site_cookies()`:
- Abre uma sessão do Chrome com o perfil especificado (deve estar logado)
- Navega em cada site de coleta (atualmente só Mercado Livre)
- Exporta cookies e localStorage usando `export_session_state()`
- Retorna um dicionário mapeando URL do site -> estado da sessão

### 2. Coleta de Produtos

Durante a coleta no modo HTTP (`use_selenium=False`):

```python
collector = MLCollector(use_selenium=False)
items = collector.run_collection()
```

Cada item é enriquecido com:
- Dados básicos do produto (nome, preço, desconto, etc.)
- Informações do vendedor (seller_id, store_name, seller_score)
- Ganho real (percentual de comissão)
- Inicialmente `url_afiliado_curta` fica como `None`

### 3. Busca em Lote de Links de Afiliado

Após enriquecer todos os itens, uma única chamada à API é feita:

```python
# Automático no _enrich_parallel quando use_selenium=False
urls = [item["url_base"] for item in items]
affiliate_mapping = collector._get_affiliate_links_batch(urls, tag="promocoesdahora")
# Retorna: {'url_original': 'https://mercadolivre.com/sec/ABC123', ...}
```

#### Detalhes da API

**Endpoint:**
```
POST https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink
```

**Headers:**
```json
{
  "accept": "application/json, text/plain, */*",
  "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
  "content-type": "application/json",
  "origin": "https://www.mercadolivre.com.br",
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
  "Cookie": "<cookies da sessão logada>"
}
```

**Body:**
```json
{
  "urls": [
    "https://produto.mercadolivre.com.br/MLB-123-produto_JM",
    "https://produto.mercadolivre.com.br/MLB-456-outro-produto_JM"
  ],
  "tag": "promocoesdahora"
}
```

**Resposta:**
```json
{
  "status": 200,
  "urls": [
    {
      "id": "1CYXyHW",
      "short_url": "https://mercadolivre.com/sec/1CYXyHW",
      "origin_url": "https://produto.mercadolivre.com.br/MLB-123-produto_JM",
      "created": true,
      "tag": "promocoesdahora"
    },
    {
      "id": "32cpb93",
      "short_url": "https://mercadolivre.com/sec/32cpb93",
      "origin_url": "https://produto.mercadolivre.com.br/MLB-456-outro-produto_JM",
      "created": true,
      "tag": "promocoesdahora"
    }
  ],
  "total_items": 2,
  "total_success": 2,
  "total_error": 0
}
```

### 4. Mapeamento de Resultados

O campo `short_url` de cada item da resposta é usado como `url_afiliado_curta`:

```python
for item in items:
    url_base = item["url_base"]
    if url_base in affiliate_mapping:
        item["url_afiliado_curta"] = affiliate_mapping[url_base]
```

## Estrutura do Código

### Principais Funções

#### `update_all_site_cookies(user_data_dir, profile_dir)`
```python
"""
Abre Chrome com perfil logado e exporta cookies de todos os sites de coleta.

Args:
    user_data_dir: Caminho para o diretório de dados do usuário do Chrome
    profile_dir: Nome do perfil (ex: "Profile 1", "Default")

Returns:
    Dict mapeando site_url -> {cookies: [...], localStorage: {...}}
"""
```

#### `MLCollector._get_affiliate_links_batch(urls, tag)`
```python
"""
Chama API de afiliados do Mercado Livre para obter links curtos em lote.

Args:
    urls: Lista de URLs de produtos
    tag: Tag do afiliado (padrão: "promocoesdahora")

Returns:
    Dict mapeando origin_url -> short_url
"""
```

#### `MLCollector._clean_url(url)`
```python
"""
Remove parâmetros de query e fragment da URL.

Args:
    url: URL completa do produto

Returns:
    URL limpa sem parâmetros
"""
```

## Configuração

### Variáveis de Ambiente

```bash
# Usar coleta via HTTP (sem Selenium)
USE_SELENIUM=false

# Diretórios do perfil do Chrome (necessário para cookies)
SELENIUM_USER_DATA_DIR=/path/to/chrome/user/data
SELENIUM_PROFILE_DIR=Profile 1

# Outras configurações
ML_MAX_PAGES=5
ML_REQUEST_DELAY_SEC=2
ML_ENRICH_WORKERS=1
```

### Banco de Dados

As mesmas variáveis podem ser configuradas na tabela `config_vars`:

```sql
INSERT INTO config_vars (key, value, is_secret, description)
VALUES 
  ('USE_SELENIUM', 'false', false, 'Usar Selenium ou HTTP para coleta'),
  ('SELENIUM_USER_DATA_DIR', '/path/to/chrome', true, 'Diretório de dados do Chrome'),
  ('SELENIUM_PROFILE_DIR', 'Profile 1', false, 'Nome do perfil do Chrome');
```

## Fluxo Completo

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Atualizar Cookies (update_all_site_cookies)             │
│    - Abre Chrome com perfil logado                          │
│    - Exporta cookies + localStorage                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Coletar Ofertas (modo HTTP)                             │
│    - Busca páginas de ofertas via HTTP                      │
│    - Extrai URLs dos produtos                               │
│    - Para cada produto:                                     │
│      * Faz requisição HTTP                                  │
│      * Extrai dados do __PRELOADED_STATE__                  │
│      * Extrai ganho_real do HTML                            │
│      * url_afiliado_curta = None (inicial)                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Buscar Links de Afiliado em Lote                        │
│    - Coleta todas as URLs dos produtos                      │
│    - Limpa URLs (remove query params)                       │
│    - Atualiza cookies novamente                             │
│    - Chama API com todas as URLs de uma vez                 │
│    - Mapeia origin_url -> short_url                         │
│    - Atualiza url_afiliado_curta de cada item               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Processar e Persistir                                   │
│    - OfferProcessor recebe itens com url_afiliado_curta     │
│    - Salva no banco de dados                                │
└─────────────────────────────────────────────────────────────┘
```

## Exemplo de Uso

### Coleta Completa

```python
from backend.modules.collectors.ml_collector import MLCollector

# Inicializa collector no modo HTTP
collector = MLCollector(use_selenium=False)

# Executa coleta (automático com links de afiliado)
items = collector.run_collection()

# Verifica resultados
for item in items:
    print(f"Produto: {item['nome_produto']}")
    print(f"  URL base: {item['url_base']}")
    print(f"  URL afiliado: {item['url_afiliado_curta']}")
    print(f"  Ganho real: {item['ganho_real']}%")
    print()
```

### Apenas Links de Afiliado

```python
from backend.modules.collectors.ml_collector import MLCollector

collector = MLCollector(use_selenium=False)

# URLs dos produtos
urls = [
    "https://produto.mercadolivre.com.br/MLB-123-produto_JM",
    "https://produto.mercadolivre.com.br/MLB-456-outro-produto_JM"
]

# Busca links de afiliado
mapping = collector._get_affiliate_links_batch(urls, tag="promocoesdahora")

# Resultado: {'url1': 'https://mercadolivre.com/sec/ABC', 'url2': '...'}
```

## Tratamento de Erros

### Cookies Inválidos ou Expirados

Se os cookies estiverem inválidos, a API retornará erro 401 ou 403. Neste caso:
1. Execute `update_all_site_cookies()` novamente
2. Verifique se o perfil do Chrome está logado
3. Verifique se `SELENIUM_USER_DATA_DIR` e `SELENIUM_PROFILE_DIR` estão corretos

### API Indisponível

Se a API retornar erro (5xx), os itens terão `url_afiliado_curta = None`.
O sistema continua funcionando normalmente, apenas sem os links de afiliado.

### URLs Inválidas

URLs que não são reconhecidas pela API serão ignoradas no mapeamento.
Verifique os logs para ver quais URLs falharam.

## Comparação: Selenium vs HTTP

| Aspecto | Selenium | HTTP (Novo) |
|---------|----------|-------------|
| **Velocidade** | ~10s por produto | ~2s para 50 produtos |
| **Recursos** | Alto (múltiplos Chrome) | Baixo (apenas HTTP) |
| **Confiabilidade** | Sujeito a mudanças de UI | API estável |
| **Paralelização** | Limitado | Batch (múltiplos de uma vez) |
| **Complexidade** | Alta | Baixa |

## Limitações

1. **Requer perfil logado**: Os cookies devem ser de uma sessão autenticada
2. **Cookies expiram**: Necessário atualizar periodicamente
3. **Rate limiting**: A API pode ter limites de requisições
4. **Apenas Mercado Livre**: Atualmente suporta apenas ML (extensível)

## Próximos Passos

- [ ] Adicionar suporte para outros sites de coleta
- [ ] Implementar cache de cookies para evitar atualizações frequentes
- [ ] Adicionar retry automático em caso de falha
- [ ] Monitorar rate limiting e ajustar delays
- [ ] Paralelizar coleta HTTP com múltiplas threads

## Referências

- [Documentação da API de Afiliados do Mercado Livre](https://developers.mercadolivre.com.br/pt_br/programa-de-afiliados)
- [SeleniumClient.export_session_state()](backend/modules/utils/selenium_client.py#L184)
- [MLCollector._get_affiliate_links_batch()](backend/modules/collectors/ml_collector.py#L202)
