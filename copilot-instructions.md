# Copilot Instructions

## Objetivo do Projeto

Este projeto é um sistema automatizado de curadoria de ofertas do Mercado Livre, com funcionalidades de:
- Coleta automatizada de ofertas via scraping (Selenium e HTTP)
- Processamento e enriquecimento de dados de produtos
- Validação inteligente baseada em critérios configuráveis
- Publicação automática em canais do Telegram
- Painel web para gerenciamento e aprovação manual
- Análise de métricas de performance

## Arquitetura do Projeto

### Backend (`backend/`)
- **`db/`**: Configuração do banco de dados SQLAlchemy
- **`models/`**: Modelos ORM (Produto, Oferta, LojaConfiavel, Tag, CanalTelegram, etc.)
- **`modules/`**:
  - **`collectors/`**: Coletores de dados (MLCollector com modo Selenium/HTTP)
  - **`services/`**: Serviços de processamento (OfferProcessor)
  - **`utils/`**: Utilitários (config, selenium_client)
  - `validator.py`: Validação de ofertas
  - `publisher.py`: Publicação no Telegram
  - `metrics_analyzer.py`: Análise de métricas
- **`routes/`**: Rotas da API REST
- **`http/`**: Cliente HTTP para requisições

### Frontend (`frontend/`)
- **`templates/`**: Templates Jinja2 para o painel web
- **`static/`**: Arquivos estáticos (CSS, JS, imagens)

### Scripts (`scripts/`)
- Scripts utilitários e pipelines de inicialização

### Arquivos Raiz
- `app.py`: Aplicação principal Flask
- `run_pipeline.py`: Pipeline completo de curadoria
- `setup_cron.sh`: Configuração de execução automatizada

## Convenções de Código

### Nomenclatura
- Use nomes de variáveis e funções em **inglês**, exceto para conceitos de domínio do negócio em português (ex: `oferta`, `produto`, `loja`, `canal`)
- Use snake_case para funções e variáveis
- Use PascalCase para classes

### Banco de Dados
- **Sempre** use SQLAlchemy ORM para acesso ao banco de dados
- **Sempre** utilize eager loading (`joinedload`, `selectinload`) para relações que serão acessadas após o fechamento da sessão
- Use `SessionLocal()` do módulo `database.py` para criar sessões
- Sempre feche as sessões após o uso (use context managers `with SessionLocal() as db:`)

### API e Rotas
- Funções que retornam dados para API devem retornar `jsonify()` e status HTTP apropriado
- Use os códigos HTTP corretos: 200 (sucesso), 201 (criado), 400 (erro do cliente), 404 (não encontrado), 500 (erro do servidor)

### Scraping e Coleta
- Funções de scraping devem ser **tolerantes a falhas** e logar erros relevantes
- Sempre adicione delays entre requisições para evitar bloqueios
- Suporte tanto modo Selenium quanto HTTP para flexibilidade

### Documentação
- Use docstrings em **português** para funções principais
- Docstrings devem descrever: objetivo, parâmetros, retorno e exceções

### Logs
- Use o módulo `logging` do Python
- Forneça logs claros para etapas críticas: coleta, enriquecimento, validação, publicação
- Nunca exponha tokens, senhas ou segredos em logs

## Boas Práticas de Segurança

- **Nunca** exponha tokens, API keys ou segredos em logs ou templates
- Use variáveis de ambiente (`.env`) para configurações sensíveis
- Sempre valide e sanitize inputs do usuário antes de processar

## Tratamento de Erros

- **Sempre** trate exceções em chamadas externas (requests, Selenium, Telegram API)
- Use try-except específicos para diferentes tipos de erro
- Faça log detalhado do erro incluindo traceback quando relevante
- Prefira continuar a execução quando possível (graceful degradation)

## Integração com Telegram

- Mensagens devem ser enviadas usando **MarkdownV2**
- Escape apenas o **texto**, nunca as URLs
- Sempre logue o erro detalhado do Telegram em caso de falha
- Valide que o bot tem permissões no canal antes de publicar

## Frontend

- Use **Bootstrap** para layout responsivo
- Cards de produtos e ofertas devem permitir alternância entre visualização em 1 ou 5 colunas
- Sempre exiba tags e canais com a capitalização original (não normalize para minúsculo)
- Use templates Jinja2 com herança para evitar duplicação

## Testes

- Sempre que possível, adicione testes unitários para funções de enriquecimento e publicação
- Testes de integração devem simular chamadas reais à API do Mercado Livre e Telegram usando **mocks**
- Use pytest como framework de testes
- Mantenha cobertura de testes acima de 70%

## Reutilização e Modularidade

- Prefira funções **puras** e reutilizáveis
- Evite duplicação de código
- Use herança e composição apropriadamente
- Mantenha funções com responsabilidade única (Single Responsibility Principle)