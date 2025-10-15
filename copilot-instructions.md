# Copilot Instructions

## Objetivo do Projeto

Este projeto realiza curadoria, enriquecimento e publicação de ofertas do Mercado Livre, com integração a Telegram, painel de aprovação e análise de métricas.

## Convenções de Código

- Use nomes de variáveis e funções em inglês, exceto quando for domínio do negócio (ex: oferta, produto, loja).
- Prefira SQLAlchemy ORM para acesso a banco de dados.
- Sempre utilize eager loading (`joinedload`, `selectinload`) para relações que serão acessadas após o fechamento da sessão.
- Funções que retornam dados para API devem retornar `jsonify` e status HTTP apropriado.
- Funções de scraping devem ser tolerantes a falhas e logar erros relevantes.
- Use docstrings em português para funções principais.

## Estrutura de Pastas

- `backend/` — código de backend (Flask, modelos, collectors, publisher, etc)
- `frontend/templates/` — templates Jinja2
- `scripts/` — scripts utilitários e pipelines

## Boas Práticas

- Nunca exponha tokens ou segredos em logs ou templates.
- Sempre trate exceções em chamadas externas (requests, Selenium, Telegram).
- Prefira funções puras e reutilizáveis.
- Use logs claros para etapas críticas (coleta, enriquecimento, publicação).

## Integração com Telegram

- Mensagens devem ser enviadas usando MarkdownV2, escapando apenas o texto, nunca a URL.
- Sempre logar o erro detalhado do Telegram em caso de falha.

## Frontend

- Use Bootstrap para layout responsivo.
- Cards de produtos e ofertas devem permitir alternância entre visualização em 1 ou 5 colunas.
- Sempre exiba as tags e canais corretos, sem normalizar para minúsculo no frontend.

## Testes

- Sempre que possível, adicione testes unitários para funções de enriquecimento e publicação.
- Testes de integração devem simular chamadas reais à API do Mercado Livre e Telegram (usar mocks).

---
```<!-- filepath: copilot-instructions.md -->
# Copilot Instructions

## Objetivo do Projeto

Este projeto realiza curadoria, enriquecimento e publicação de ofertas do Mercado Livre, com integração a Telegram, painel de aprovação e análise de métricas.

## Convenções de Código

- Use nomes de variáveis e funções em inglês, exceto quando for domínio do negócio (ex: oferta, produto, loja).
- Prefira SQLAlchemy ORM para acesso a banco de dados.
- Sempre utilize eager loading (`joinedload`, `selectinload`) para relações que serão acessadas após o fechamento da sessão.
- Funções que retornam dados para API devem retornar `jsonify` e status HTTP apropriado.
- Funções de scraping devem ser tolerantes a falhas e logar erros relevantes.
- Use docstrings em português para funções principais.

## Estrutura de Pastas

- `backend/` — código de backend (Flask, modelos, collectors, publisher, etc)
- `frontend/templates/` — templates Jinja2
- `scripts/` — scripts utilitários e pipelines

## Boas Práticas

- Nunca exponha tokens ou segredos em logs ou templates.
- Sempre trate exceções em chamadas externas (requests, Selenium, Telegram).
- Prefira funções puras e reutilizáveis.
- Use logs claros para etapas críticas (coleta, enriquecimento, publicação).

## Integração com Telegram

- Mensagens devem ser enviadas usando MarkdownV2, escapando apenas o texto, nunca a URL.
- Sempre logar o erro detalhado do Telegram em caso de falha.

## Frontend

- Use Bootstrap para layout responsivo.
- Cards de produtos e ofertas devem permitir alternância entre visualização em 1 ou 5 colunas.
- Sempre exiba as tags e canais corretos, sem normalizar para minúsculo no frontend.

## Testes

- Sempre que possível, adicione testes unitários para funções de enriquecimento e publicação.
- Testes de integração devem simular chamadas reais à API do Mercado Livre e Telegram (usar mocks).

---