# Fluxo de Coleta e Parsing de Links

Este documento descreve o novo fluxo de coleta de ofertas implementado para otimizar o processamento e permitir parsing paralelo.

## Visão Geral

O fluxo foi dividido em duas fases principais:

1. **Fase de Coleta**: Coleta apenas os links das ofertas
2. **Fase de Parsing**: Processa os links coletados em paralelo

## Arquitetura

### Tabela `links_coleta`

Nova tabela que armazena links coletados antes do parsing:

```sql
CREATE TABLE links_coleta (
    id INTEGER PRIMARY KEY,
    url VARCHAR NOT NULL,
    source VARCHAR NOT NULL,              -- origem: "mercadolivre", "amazon", etc.
    ativo BOOLEAN NOT NULL DEFAULT TRUE,   -- false após parsing bem-sucedido
    criado_em DATETIME NOT NULL,
    parseado_em DATETIME,
    tentativas INTEGER NOT NULL DEFAULT 0,
    ultimo_erro VARCHAR,
    UNIQUE (url, source)                   -- previne duplicatas
);
```

**Índices**:
- `url`, `source`: Para buscas rápidas
- `ativo`: Para filtrar links pendentes
- `criado_em`: Para ordenação e TTL

### Componentes

#### 1. `LinkService` (`backend/modules/services/link_service.py`)

Gerencia o ciclo de vida dos links:

- `save_links()`: Salva links coletados (ignora duplicatas)
- `get_active_links()`: Recupera links ativos para parsing
- `mark_as_parsed()`: Marca link como parseado (inativa)
- `mark_as_failed()`: Registra falha (mantém ativo para retry)
- `cleanup_expired_links()`: Remove links com TTL expirado

#### 2. `LinkParser` (`backend/modules/services/link_parser.py`)

Gerencia parsing paralelo:

- Cria múltiplas threads, cada uma com:
  - Sua própria sessão de DB
  - Seu próprio collector (MLCollector)
  - Seu próprio driver Selenium
- Processa links de forma thread-safe
- Atualiza status dos links após processing

#### 3. `MLCollector` (modificado)

Agora suporta dois modos:

- `run_collection()`: Coleta apenas links (sem parsing)
- `parse_link(url)`: Faz parsing detalhado de um link específico

## Fluxo do Pipeline

### 1. Coleta de Links

```python
ml_collector = MLCollector()
links = ml_collector.run_collection()  # Retorna lista de URLs
```

### 2. Persistência

```python
link_service = LinkService(db)
inserted = link_service.save_links(links, source="mercadolivre")
```

### 3. Limpeza de Expirados (TTL)

```python
expired = link_service.cleanup_expired_links(ttl_hours=24)
```

### 4. Parsing Paralelo

```python
link_parser = LinkParser(db)
stats = link_parser.parse_active_links(source="mercadolivre")
# stats = {"total": 100, "success": 95, "failed": 5}
```

### 5. Processamento de Ofertas

Para cada link parseado com sucesso:
- Extrai dados do produto
- Cria/atualiza produto no banco
- Cria oferta se elegível
- Marca link como inativo

Para links com falha:
- Incrementa contador de tentativas
- Registra erro
- Mantém link ativo para retry

## Vantagens do Novo Fluxo

### 1. Performance
- Parsing paralelo com múltiplas threads
- Cada thread tem seu próprio driver Selenium
- Não há bloqueio de recursos compartilhados

### 2. Resiliência
- Links com falha são mantidos ativos para retry
- Contador de tentativas permite implementar limite de retries
- TTL evita acúmulo de links não processáveis

### 3. Rastreabilidade
- Histórico de tentativas
- Registro de erros
- Timestamp de coleta e parsing

### 4. Sem Duplicatas
- Constraint único em (url, source)
- Evita processar o mesmo link múltiplas vezes
- Possibilidade de reativar links inativos

## Configuração

Variáveis de ambiente (via `config.env` ou `get_config()`):

```bash
# Número de workers para parsing paralelo (padrão: 3)
LINK_PARSER_WORKERS=5

# Páginas a coletar do ML (padrão: 1)
ML_MAX_PAGES=3

# Workers para enriquecimento do ML (padrão: 1)
ML_ENRICH_WORKERS=1

# Delay entre requisições (padrão: 2)
ML_REQUEST_DELAY_SEC=2
```

## Exemplo de Uso

```python
from backend.db.database import SessionLocal
from backend.modules.collectors.ml_collector import MLCollector
from backend.modules.services.link_service import LinkService
from backend.modules.services.link_parser import LinkParser

# Inicializar
db = SessionLocal()

# 1. Coletar links
collector = MLCollector()
links = collector.run_collection()
print(f"Links coletados: {len(links)}")

# 2. Salvar links
link_service = LinkService(db)
inserted = link_service.save_links(links, source="mercadolivre")
print(f"Links novos: {inserted}")

# 3. Limpar expirados
expired = link_service.cleanup_expired_links(ttl_hours=24)
print(f"Links expirados removidos: {expired}")

# 4. Parsear links ativos
parser = LinkParser(db)
try:
    stats = parser.parse_active_links(source="mercadolivre")
    print(f"Parsing: {stats}")
finally:
    parser.cleanup()
    db.close()
```

## Comportamento de Parsing por Origem

### Mercado Livre (`source="mercadolivre"`)

O parser usa `MLCollector.parse_link()` que:

1. Abre a página do produto
2. Extrai dados do `__PRELOADED_STATE__`
3. Obtém seller_id, store_name, preços, etc.
4. Gera link de afiliado curto
5. Extrai ganho real (percentual de comissão)

### Outras Origens

Para adicionar suporte a novas origens:

1. Criar novo Collector (ex: `AmazonCollector`)
2. Implementar método `parse_link(url)`
3. Adicionar lógica no `LinkParser._parse_single_link()`

```python
if link.source == "mercadolivre":
    collector = MLCollector()
elif link.source == "amazon":
    collector = AmazonCollector()
else:
    raise ValueError(f"Source não suportada: {link.source}")
```

## Monitoramento

Para verificar o status dos links:

```sql
-- Links ativos por origem
SELECT source, COUNT(*) as total
FROM links_coleta
WHERE ativo = 1
GROUP BY source;

-- Links com múltiplas falhas
SELECT id, url, tentativas, ultimo_erro
FROM links_coleta
WHERE ativo = 1 AND tentativas > 3
ORDER BY tentativas DESC;

-- Links parseados hoje
SELECT COUNT(*) as total
FROM links_coleta
WHERE parseado_em >= date('now')
AND ativo = 0;

-- Taxa de sucesso
SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN ativo = 0 THEN 1 ELSE 0 END) as sucesso,
    ROUND(100.0 * SUM(CASE WHEN ativo = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as taxa_sucesso
FROM links_coleta
WHERE criado_em >= datetime('now', '-1 day');
```

## Troubleshooting

### Links não sendo parseados

1. Verificar se há links ativos:
   ```sql
   SELECT COUNT(*) FROM links_coleta WHERE ativo = 1;
   ```

2. Verificar erros recentes:
   ```sql
   SELECT url, tentativas, ultimo_erro 
   FROM links_coleta 
   WHERE ativo = 1 
   ORDER BY tentativas DESC 
   LIMIT 10;
   ```

### Performance baixa

1. Aumentar `LINK_PARSER_WORKERS`
2. Verificar se há links duplicados acumulados
3. Executar cleanup de links expirados

### Memória alta

1. Reduzir `LINK_PARSER_WORKERS`
2. Reduzir `ML_MAX_PAGES`
3. Executar cleanup mais frequente

## Testes

Execute o teste de validação:

```bash
python3 test_link_collection.py
```

Este teste valida:
- Salvamento de links
- Prevenção de duplicatas
- Recuperação de links ativos
- Marcação de parsing bem-sucedido
- Marcação de falhas
- TTL e cleanup
