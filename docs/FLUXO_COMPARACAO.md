# Comparação: Fluxo Antigo vs Novo

## Fluxo Antigo (Antes)

```
┌─────────────────────┐
│   MLCollector       │
│  run_collection()   │
└──────────┬──────────┘
           │
           │ Para cada página:
           │ 1. Busca HTML
           │ 2. Extrai links
           │ 3. Abre cada link
           │ 4. Faz parsing completo (LENTO)
           │ 5. Extrai todos os dados
           │
           ▼
┌─────────────────────┐
│  Lista de Ofertas   │
│  Completas (items)  │
└──────────┬──────────┘
           │
           │ Para cada item:
           ▼
┌─────────────────────┐
│  OfferProcessor     │
│  process_item()     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Banco de Dados     │
│  (Produto, Oferta)  │
└─────────────────────┘
```

**Problemas:**
- ❌ Parsing sequencial (lento)
- ❌ Um erro interrompe toda a coleta
- ❌ Sem retry para falhas
- ❌ Mesmos links podem ser processados múltiplas vezes
- ❌ Não há persistência intermediária

## Fluxo Novo (Depois)

```
┌─────────────────────────────────────────────────────┐
│                   FASE 1: COLETA                    │
└─────────────────────────────────────────────────────┘

┌─────────────────────┐
│   MLCollector       │
│  run_collection()   │
└──────────┬──────────┘
           │
           │ Para cada página:
           │ 1. Busca HTML
           │ 2. Extrai APENAS links
           │ 3. Retorna URLs (RÁPIDO)
           │
           ▼
┌─────────────────────┐
│  Lista de Links     │
│  [{url, source}]    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   LinkService       │
│   save_links()      │
└──────────┬──────────┘
           │
           │ - Ignora duplicatas
           │ - Reativa inativos
           ▼
┌─────────────────────┐
│  Tabela             │
│  links_coleta       │
│  (persistência)     │
└──────────┬──────────┘
           │
┌──────────┴──────────┐
│  TTL Cleanup        │
│  (remove expirados) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────────────┐
│                   FASE 2: PARSING                   │
└─────────────────────────────────────────────────────┘

┌─────────────────────┐
│   LinkParser        │
│ parse_active_links()│
└──────────┬──────────┘
           │
           │ Busca links ativos
           │ Cria N threads paralelas
           ▼
    ┌──────┴──────┬──────┬──────┐
    │             │      │      │
    ▼             ▼      ▼      ▼
┌────────┐  ┌────────┐  ...  ┌────────┐
│Thread 1│  │Thread 2│       │Thread N│
│        │  │        │       │        │
│ DB     │  │ DB     │       │ DB     │
│Session │  │Session │       │Session │
│        │  │        │       │        │
│ML      │  │ML      │       │ML      │
│Collect.│  │Collect.│       │Collect.│
│        │  │        │       │        │
│Selenium│  │Selenium│       │Selenium│
└────┬───┘  └────┬───┘       └────┬───┘
     │           │                 │
     │ Para cada link:             │
     │ 1. Abre URL                 │
     │ 2. Parse completo           │
     │ 3. Processa oferta          │
     │ 4. Marca como parseado ✓    │
     │    ou falha (retry)         │
     │                             │
     └─────────────┬───────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  LinkService    │
         │ mark_as_parsed()│
         │ ou              │
         │ mark_as_failed()│
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ links_coleta    │
         │ (ativo=false)   │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Banco de Dados  │
         │(Produto, Oferta)│
         └─────────────────┘
```

## Comparação de Características

| Característica | Fluxo Antigo | Fluxo Novo |
|----------------|--------------|------------|
| **Performance** | Sequencial, lento | Paralelo, rápido ✓ |
| **Resiliência** | Falha interrompe tudo | Retry automático ✓ |
| **Duplicatas** | Possíveis | Prevenidas ✓ |
| **Rastreabilidade** | Limitada | Completa ✓ |
| **Persistência** | Apenas final | Intermediária ✓ |
| **TTL** | Não | Sim (24h) ✓ |
| **Thread-safety** | N/A | Sim ✓ |
| **Escalabilidade** | Limitada | Alta ✓ |

## Benefícios Mensuráveis

### Velocidade
- **Antes**: N links × tempo_parsing (sequencial)
- **Depois**: N links ÷ workers × tempo_parsing (paralelo)
- **Ganho**: ~3-5x mais rápido (com 3-5 workers)

### Resiliência
- **Antes**: 1 falha = pipeline parado
- **Depois**: Falhas isoladas, retry automático

### Recursos
- **Antes**: 1 sessão Selenium compartilhada (bloqueio)
- **Depois**: N sessões independentes (sem bloqueio)

## Configuração Recomendada

Para otimizar performance:

```bash
# config.env

# Coleta mais páginas (mais links)
ML_MAX_PAGES=5

# Parsing paralelo (ajuste conforme CPU/RAM)
LINK_PARSER_WORKERS=3

# Workers de enriquecimento ML (mantenha baixo)
ML_ENRICH_WORKERS=1

# Delay entre requisições
ML_REQUEST_DELAY_SEC=2
```

## Próximos Passos Possíveis

1. **Limite de Tentativas**: Desativar links após N falhas
2. **Priorização**: Processar links por prioridade/fonte
3. **Agendamento**: Parsing em horários específicos
4. **Métricas**: Dashboard de performance em tempo real
5. **Notificações**: Alertas para falhas críticas
