# Especificação Técnica do Backend - Fase 1: Curadoria de Ofertas Automatizada

## 1. Introdução

Este documento detalha a especificação técnica do backend para a Fase 1 do projeto de curadoria de ofertas automatizadas. O objetivo principal desta fase é desenvolver um sistema robusto e escalável capaz de identificar, validar e distribuir ofertas de produtos de plataformas de e-commerce (inicialmente Amazon e Mercado Livre) para canais de mensageria (inicialmente Telegram), com um painel de controle web para curadoria humana. A arquitetura proposta visa a modularidade, a resiliência e a capacidade de expansão para futuras fases do projeto, como a integração com WhatsApp e Instagram, e a monetização B2B.

### 1.1. Objetivo

O objetivo deste backend é fornecer a infraestrutura lógica e de dados necessária para:

*   Automatizar a coleta de dados de ofertas de e-commerce.
*   Construir e manter um histórico de preços proprietário para validação de ofertas.
*   Aplicar regras de negócio complexas para determinar a validade e a relevância de uma oferta.
*   Gerenciar a categorização de produtos através de um sistema de tags.
*   Controlar a distribuição de ofertas para canais de mensageria específicos.
*   Fornecer APIs para o painel de controle web, permitindo a curadoria humana e a gestão de configurações.
*   Coletar e disponibilizar métricas de desempenho (cliques, vendas) para análise e apresentação.

### 1.2. Escopo da Fase 1

Esta especificação abrange o backend necessário para suportar as funcionalidades visuais das telas de Login, Fila de Aprovação, Ofertas Publicadas e Configurações, conforme detalhado nos mockups de frontend. Inclui a lógica de scraping, validação, gerenciamento de dados e integração com a API do Telegram e Bitly.

### 1.3. Tecnologias Selecionadas

As tecnologias foram escolhidas com base na compatibilidade com o ambiente Raspberry Pi, facilidade de desenvolvimento, escalabilidade inicial e custo-benefício.

*   **Linguagem de Programação**: Python 3.x
*   **Framework Web**: Flask (para o painel de controle administrativo)
*   **Banco de Dados**: SQLite (para persistência de dados local)
*   **Bibliotecas Principais**: 
    *   `requests` (para requisições HTTP)
    *   `BeautifulSoup4` (para web scraping, se necessário)
    *   `python-telegram-bot` (para interação com a API do Telegram)
    *   `boto3` (para interação com a API da Amazon, se aplicável)
    *   `mercadolibre` SDK (para interação com a API do Mercado Livre, se aplicável)
    *   `bitly-api-python` (para encurtamento de URLs e coleta de cliques)
    *   `Flask-Login` (para autenticação de usuários no painel)
    *   `SQLAlchemy` ou `Flask-SQLAlchemy` (ORM para interação com o banco de dados)

## 2. Arquitetura Geral do Sistema

A arquitetura do backend será modular, baseada em microsserviços lógicos (embora implementados como módulos Python dentro de uma aplicação maior para simplificar a implantação no Raspberry Pi). A comunicação entre os módulos e o frontend será predominantemente via banco de dados SQLite e APIs RESTful.

```mermaid
graph TD
    A[Cron Jobs / Scheduler] --> B(Módulo de Coleta/Scraping)
    B --> C(Banco de Dados SQLite)
    C --> D(Módulo de Validação de Ofertas)
    D --> C
    C --> E(Módulo de Publicação de Ofertas)
    E --> F[API Telegram]
    E --> G[API Bitly]
    H[Navegador Web] --> I(Painel Administrativo Web - Flask)
    I --> C
    J[Cron Jobs / Scheduler] --> K(Módulo de Análise de Métricas)
    K --> C
    K --> G
    K --> L[APIs de Afiliados (Amazon/ML)]
```

### 2.1. Componentes Principais

*   **Banco de Dados SQLite**: O coração do sistema, armazenando todas as informações de produtos, ofertas, histórico de preços, configurações e métricas.
*   **Módulo de Coleta/Scraping**: Responsável por interagir com as APIs da Amazon e Mercado Livre (e potencialmente web scraping de comparadores de preço) para buscar novas ofertas e dados de produtos.
*   **Módulo de Validação de Ofertas**: Aplica a lógica de negócio para determinar a 


validade e a qualidade de uma oferta, utilizando o histórico de preços próprio e, se possível, dados de comparadores externos.
*   **Módulo de Publicação de Ofertas**: Encarregado de formatar as mensagens e enviá-las para os canais de mensageria (Telegram) e de interagir com a API do Bitly para encurtamento de URLs e rastreamento de cliques.
*   **Painel Administrativo Web (Flask)**: A interface de usuário para curadoria, gerenciamento de configurações e visualização de métricas. Interage com o banco de dados via ORM (SQLAlchemy).
*   **Módulo de Análise de Métricas**: Coleta dados de cliques do Bitly e de vendas das plataformas de afiliados para gerar relatórios e insights.
*   **Scheduler (Cron Jobs)**: Orquestra a execução periódica dos módulos de coleta, validação e análise de métricas.

## 3. Design do Banco de Dados (SQLite)

O banco de dados SQLite será o repositório central de todas as informações do sistema. A escolha do SQLite se deve à sua leveza, facilidade de uso em ambientes embarcados como o Raspberry Pi e a ausência de necessidade de um servidor de banco de dados dedicado. As tabelas serão projetadas para suportar as funcionalidades descritas e as telas do frontend.

### 3.1. Tabelas e Relacionamentos

#### 3.1.1. `usuarios`
Armazena as credenciais para acesso ao painel administrativo.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único do usuário. |
| `username` | TEXT | UNIQUE, NOT NULL | Nome de usuário para login. |
| `password_hash` | TEXT | NOT NULL | Hash da senha do usuário (usar bcrypt). |
| `email` | TEXT | UNIQUE, NOT NULL | Endereço de e-mail do usuário. |
| `is_admin` | BOOLEAN | NOT NULL, DEFAULT 0 | Indica se o usuário tem privilégios administrativos. |

#### 3.1.2. `lojas_confiaveis`
Gerencia as lojas/vendedores dos quais o sistema buscará ofertas. Corresponde à seção 


Gerenciar Lojas Confiáveis` na tela de Configurações.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único da loja. |
| `nome_loja` | TEXT | UNIQUE, NOT NULL | Nome amigável da loja (ex: "Amazon.com.br", "Magazine Luiza"). |
| `plataforma` | TEXT | NOT NULL | Plataforma de e-commerce (ex: "Amazon", "Mercado Livre"). |
| `id_loja_api` | TEXT | NULLABLE | ID ou identificador interno da loja na API da plataforma (se aplicável). |
| `pontuacao_confianca` | INTEGER | NOT NULL, DEFAULT 3 | Pontuação de 1 a 5 para a reputação da loja. |
| `ativa` | BOOLEAN | NOT NULL, DEFAULT 1 | Indica se o sistema deve buscar ofertas desta loja. |

#### 3.1.3. `tags`
Define as categorias/tags para organização de produtos e canais. Corresponde à seção `Gerenciar Tags` na tela de Configurações.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único da tag. |
| `nome_tag` | TEXT | UNIQUE, NOT NULL | Nome da tag (ex: "informatica", "gamer", "cozinha"). |

#### 3.1.4. `canais_telegram`
Gerencia os canais do Telegram para onde as ofertas serão publicadas. Corresponde à seção `Gerenciar Canais` na tela de Configurações.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único do canal. |
| `id_canal_api` | TEXT | UNIQUE, NOT NULL | ID do chat/canal no Telegram (obtido via Bot API). |
| `nome_amigavel` | TEXT | NOT NULL | Nome amigável do canal (ex: "Ofertas de PC - Telegram"). |
| `ativo` | BOOLEAN | NOT NULL, DEFAULT 1 | Indica se o canal está ativo para recebimento de ofertas. |
| `inscritos` | INTEGER | NOT NULL, DEFAULT 0 | Número de inscritos no canal (para métricas). |

#### 3.1.5. `canal_tags`
Tabela de ligação N:N entre `canais_telegram` e `tags`. Permite que um canal tenha múltiplas tags e uma tag esteja associada a múltiplos canais.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `canal_id` | INTEGER | PRIMARY KEY, FOREIGN KEY | Referência ao `id` da tabela `canais_telegram`. |
| `tag_id` | INTEGER | PRIMARY KEY, FOREIGN KEY | Referência ao `id` da tabela `tags`. |

#### 3.1.6. `produtos`
Catálogo central de todos os produtos que já foram identificados pelo sistema, independentemente de estarem em oferta no momento. Serve como base para o histórico de preços.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único do produto no sistema. |
| `product_id_loja` | TEXT | UNIQUE, NOT NULL | ID único do produto na loja (ASIN para Amazon, SKU para Mercado Livre). |
| `nome_produto` | TEXT | NOT NULL | Nome completo do produto. |
| `url_base` | TEXT | NOT NULL | URL base do produto na loja (antes de adicionar parâmetros de afiliado). |
| `imagem_url` | TEXT | NULLABLE | URL da imagem principal do produto. |

#### 3.1.7. `produto_tags`
Tabela de ligação N:N entre `produtos` e `tags`. Permite que um produto tenha múltiplas tags.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `produto_id` | INTEGER | PRIMARY KEY, FOREIGN KEY | Referência ao `id` da tabela `produtos`. |
| `tag_id` | INTEGER | PRIMARY KEY, FOREIGN KEY | Referência ao `id` da tabela `tags`. |

#### 3.1.8. `historico_precos`
Armazena o histórico de preços de cada produto, essencial para a validação de ofertas. Esta é a base para a regra de "menor preço dos últimos X dias/meses".

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único do registro de preço. |
| `produto_id` | INTEGER | NOT NULL, FOREIGN KEY | Referência ao `id` da tabela `produtos`. |
| `loja_id` | INTEGER | NOT NULL, FOREIGN KEY | Referência ao `id` da tabela `lojas_confiaveis` (para saber de qual loja veio o preço). |
| `preco` | REAL | NOT NULL | Preço do produto no momento da coleta. |
| `data_verificacao` | DATETIME | NOT NULL | Timestamp da coleta do preço. |

#### 3.1.9. `ofertas`
Armazena as ofertas encontradas pelo scraper, seu status de validação e informações para o painel de curadoria. Corresponde aos cards na tela `Fila de Aprovação` e aos registros na tela `Ofertas Publicadas`.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único da oferta. |
| `produto_id` | INTEGER | NOT NULL, FOREIGN KEY | Referência ao `id` da tabela `produtos`. |
| `loja_id` | INTEGER | NOT NULL, FOREIGN KEY | Referência ao `id` da tabela `lojas_confiaveis`. |
| `preco_original` | REAL | NULLABLE | Preço "de" informado pela loja. |
| `preco_oferta` | REAL | NOT NULL | Preço atual da oferta. |
| `url_afiliado_longa` | TEXT | NOT NULL | URL de afiliado completa gerada. |
| `url_afiliado_curta` | TEXT | NULLABLE | URL encurtada pelo Bitly. |
| `data_encontrado` | DATETIME | NOT NULL | Data e hora em que a oferta foi encontrada. |
| `data_validade` | DATETIME | NULLABLE | Data de expiração da oferta (se informada pela loja). |
| `status` | TEXT | NOT NULL | Status da oferta: `PENDENTE_APROVACAO`, `APROVADO`, `REJEITADO`, `AGENDADO`, `PUBLICADO`. |
| `motivo_validacao` | TEXT | NULLABLE | Texto gerado pelo módulo de validação (ex: "Menor preço dos últimos 90 dias"). |
| `data_publicacao` | DATETIME | NULLABLE | Data e hora em que a oferta foi efetivamente publicada. |
| `mensagem_id_telegram` | TEXT | NULLABLE | ID da mensagem no Telegram (para rastreamento/edição). |

#### 3.1.10. `metricas_ofertas`
Armazena as métricas de desempenho de cada oferta publicada, obtidas via Bitly e relatórios de afiliados. Corresponde às colunas de métricas na tela `Ofertas Publicadas`.

| Campo | Tipo | Restrições | Descrição |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | Identificador único da métrica. |
| `oferta_id` | INTEGER | NOT NULL, FOREIGN KEY | Referência ao `id` da tabela `ofertas`. |
| `cliques` | INTEGER | NOT NULL, DEFAULT 0 | Número de cliques no link encurtado. |
| `vendas` | INTEGER | NOT NULL, DEFAULT 0 | Número de vendas atribuídas a esta oferta. |
| `data_atualizacao` | DATETIME | NOT NULL | Última atualização das métricas. |

### 3.2. Considerações sobre o Banco de Dados

*   **ORM**: Recomenda-se o uso de um ORM como SQLAlchemy ou Flask-SQLAlchemy para abstrair as operações SQL e facilitar a interação do Python com o banco de dados.
*   **Migrações**: Para futuras alterações no esquema do banco de dados, ferramentas de migração (ex: Alembic) devem ser consideradas para gerenciar as versões do banco de forma controlada.
*   **Índices**: Índices devem ser criados em colunas frequentemente consultadas (ex: `product_id_loja` em `produtos`, `data_verificacao` em `historico_precos`, `status` em `ofertas`) para otimizar o desempenho das consultas.

## 4. Módulos do Backend e Lógica de Negócio

### 4.1. Módulo de Coleta/Scraping (`collector.py`)

**Responsabilidades:**
*   Buscar novas ofertas nas plataformas de e-commerce configuradas.
*   Atualizar o catálogo de produtos (`produtos`) e o histórico de preços (`historico_precos`).
*   Identificar e inserir novas ofertas na tabela `ofertas` com status `PENDENTE_APROVACAO`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Configurações**: Consulta a tabela `lojas_confiaveis` para identificar quais lojas estão ativas e qual sua pontuação de confiança.
2.  **Iteração por Plataforma/Loja**: Para cada plataforma (Amazon, Mercado Livre):
    *   Utiliza a API oficial (preferencialmente) ou web scraping (se API não disponível ou limitada) para buscar ofertas.
    *   **Amazon**: Utilizar a Product Advertising API (PA-API). Necessita de credenciais de Associado Amazon. A busca pode ser por categorias, palavras-chave ou listas de produtos.
    *   **Mercado Livre**: Utilizar a API do Mercado Livre. Necessita de credenciais de desenvolvedor. A busca pode ser por termos, categorias e filtros de preço/desconto.
    *   **Web Scraping (Alternativa/Complemento)**: Se APIs não forem suficientes para identificar ofertas com desconto, pode-se implementar web scraping. **Atenção**: Web scraping é frágil e pode ser bloqueado. Deve ser uma alternativa de último recurso e com mecanismos de resiliência (rotação de IPs, user-agents, tratamento de CAPTCHAs).
3.  **Processamento de Produtos Encontrados**:
    *   Para cada produto/oferta encontrada:
        *   Verifica se o `product_id_loja` já existe na tabela `produtos`. Se não, insere um novo registro.
        *   Insere o preço atual na tabela `historico_precos`, associando-o ao `produto_id` e `loja_id`.
        *   **Identificação de Oferta**: Compara o `preco_oferta` com o `preco_original` (se disponível) ou com o `preco` mais recente no `historico_precos` para determinar se é uma oferta válida para consideração.
        *   **Criação de Oferta Pendente**: Se for uma oferta válida, insere um novo registro na tabela `ofertas` com `status = 'PENDENTE_APROVACAO'`, preenchendo `produto_id`, `loja_id`, `preco_original`, `preco_oferta`, `url_afiliado_longa`, `data_encontrado` e `data_validade` (se disponível).
        *   **Categorização Inicial (Tags)**: Baseado no `nome_produto` e/ou categoria fornecida pela API da loja, o módulo deve sugerir tags para o produto. Isso pode ser feito com um dicionário de palavras-chave para tags (ex: "notebook" -> #informatica, "geladeira" -> #eletrodomestico). As tags sugeridas são armazenadas na tabela `produto_tags`.

### 4.2. Módulo de Validação de Ofertas (`validator.py`)

**Responsabilidades:**
*   Aplicar regras de negócio para qualificar as ofertas `PENDENTE_APROVACAO`.
*   Atualizar o `status` da oferta para `APROVADO` ou `REJEITADO` e preencher o `motivo_validacao`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Ofertas Pendentes**: Consulta a tabela `ofertas` por registros com `status = 'PENDENTE_APROVACAO'`.
2.  **Iteração por Oferta**:
    *   **Verificação de Desconto Real (Baseado no Histórico Próprio)**:
        *   Consulta a tabela `historico_precos` para o `produto_id` da oferta.
        *   Calcula o menor preço e o preço médio dos últimos 30, 60 e 90 dias (conforme regras de negócio).
        *   **Regra**: Se `preco_oferta` for o menor preço dos últimos 60 dias OU `preco_oferta` for X% (ex: 10%) menor que o preço médio dos últimos 30 dias, a oferta é pré-aprovada.
        *   Preenche o `motivo_validacao` (ex: "Menor preço dos últimos 90 dias", "X% abaixo da média").
    *   **Comparação com Comparadores Externos (Opcional/Secundário)**:
        *   **Atenção**: Esta etapa é de ALTO RISCO e FRAGILIDADE devido ao web scraping. Deve ser implementada com cautela.
        *   Para produtos da Amazon, tenta buscar o histórico no CamelCamelCamel. Para outros, no Zoom.
        *   Se dados confiáveis forem obtidos, eles podem ser usados para reforçar a validação ou como um critério adicional.
        *   Os dados obtidos são armazenados na tabela `verificacao_precos` (se implementada).
    *   **Regra de Duplicidade/Melhor Preço**: Verifica se o mesmo `produto_id_loja` (ou um identificador similar) já existe em outra oferta `PENDENTE_APROVACAO` ou `APROVADO` com um preço menor. Se sim, a oferta atual é marcada como `REJEITADO`.
    *   **Atualização de Status**: Se a oferta passar por todas as regras de validação, seu `status` é atualizado para `APROVADO` (se a curadoria for totalmente automática) ou permanece `PENDENTE_APROVACAO` (se for para revisão humana no painel, que é o caso atual). O `motivo_validacao` é atualizado.

### 4.3. Módulo de Publicação de Ofertas (`publisher.py`)

**Responsabilidades:**
*   Processar ofertas com `status = 'APROVADO'` ou `AGENDADO`.
*   Encurtar URLs de afiliado via Bitly.
*   Formatar mensagens e publicá-las nos canais do Telegram.
*   Atualizar o status da oferta para `PUBLICADO`.

**Fluxo de Execução (via Scheduler ou acionado pelo Painel Web):**
1.  **Leitura de Ofertas Aprovadas/Agendadas**: Consulta a tabela `ofertas` por registros com `status = 'APROVADO'` ou `AGENDADO` (e `data_publicacao` <= data/hora atual para agendados).
2.  **Iteração por Oferta**:
    *   **Encurtamento de URL**: Se `url_afiliado_curta` estiver vazio, chama a API do Bitly para encurtar `url_afiliado_longa`. Armazena o link curto e o `link_id` do Bitly (para métricas) na tabela `ofertas`.
    *   **Determinação de Canais de Destino**: 
        *   Consulta a tabela `produto_tags` para obter as tags do produto.
        *   Consulta a tabela `canal_tags` para encontrar todos os `canais_telegram` ativos que estão associados a pelo menos uma das tags do produto.
    *   **Formatação da Mensagem**: Constrói a mensagem a ser enviada para o Telegram, incluindo:
        *   Nome do produto.
        *   Preço da oferta e, opcionalmente, preço original riscado.
        *   `motivo_validacao` (ex: "Menor preço dos últimos 90 dias").
        *   URL encurtada do Bitly.
        *   Emojis e formatação para chamar a atenção.
    *   **Publicação no Telegram**: Utiliza a API do Bot do Telegram para enviar a mensagem para cada `id_canal_api` determinado.
        *   **Tratamento de Erros**: Implementar retry logic para falhas temporárias da API do Telegram.
        *   Armazena o `mensagem_id_telegram` retornado pela API na tabela `ofertas`.
    *   **Atualização de Status**: Atualiza o `status` da oferta para `PUBLICADO` e `data_publicacao` na tabela `ofertas`.

### 4.4. Módulo de Análise de Métricas (`metrics_analyzer.py`)

**Responsabilidades:**
*   Coletar dados de cliques do Bitly.
*   Coletar dados de vendas das plataformas de afiliados.
*   Atualizar a tabela `metricas_ofertas`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Ofertas Publicadas**: Consulta a tabela `ofertas` por registros com `status = 'PUBLICADO'`.
2.  **Iteração por Oferta Publicada**:
    *   **Coleta de Cliques (Bitly)**: Utiliza a API do Bitly para obter o número de cliques para a `url_afiliado_curta` (usando o `link_id` do Bitly).
    *   **Coleta de Vendas (APIs de Afiliados)**: 
        *   **Amazon/Mercado Livre**: A forma mais confiável é através dos relatórios de vendas das APIs de afiliados, usando os `Tracking IDs` ou `Sub-IDs` que foram gerados na `url_afiliado_longa`.
        *   **Desafio**: A obtenção de dados de vendas via API pode ser complexa e nem sempre em tempo real. Pode ser necessário um processo semi-manual de importação de relatórios em CSV para o banco de dados, especialmente no início.
    *   **Atualização de Métricas**: Atualiza ou insere um registro na tabela `metricas_ofertas` com os `cliques`, `vendas` e `data_atualizacao`.

## 5. Painel Administrativo Web (Flask)

O painel web será a interface para o usuário interagir com o sistema. Ele será construído com Flask e interagirá com o banco de dados SQLite.

### 5.1. Rotas e Endpoints da API

#### 5.1.1. Autenticação
*   `GET /login`: Renderiza a tela de login.
*   `POST /login`: Autentica o usuário. Se sucesso, redireciona para `/dashboard`. Se falha, exibe erro.
*   `GET /logout`: Desloga o usuário e redireciona para `/login`.

#### 5.1.2. Fila de Aprovação (Tela Principal)
*   `GET /dashboard` ou `GET /`: Renderiza a tela `Fila de Aprovação`.
    *   **Dados**: Consulta a tabela `ofertas` por `status = 'PENDENTE_APROVACAO'`. Retorna todos os dados necessários para renderizar os cards (nome, imagem, preços, motivo validação, tags sugeridas, canais de destino).
*   `POST /ofertas/<id>/aprovar`: 
    *   **Parâmetros**: `id` da oferta, `tags` (lista de strings).
    *   **Ação**: Atualiza as tags do produto (`produto_tags`). Atualiza o `status` da oferta para `APROVADO` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.
*   `POST /ofertas/<id>/rejeitar`: 
    *   **Parâmetros**: `id` da oferta.
    *   **Ação**: Atualiza o `status` da oferta para `REJEITADO` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.
*   `POST /ofertas/<id>/agendar`: 
    *   **Parâmetros**: `id` da oferta, `data_agendamento` (datetime).
    *   **Ação**: Atualiza o `status` da oferta para `AGENDADO` e define `data_publicacao` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.

#### 5.1.3. Ofertas Publicadas
*   `GET /publicadas`: Renderiza a tela `Ofertas Publicadas`.
    *   **Dados**: Consulta a tabela `ofertas` por `status = 'PUBLICADO'`. Realiza JOIN com `metricas_ofertas` para obter cliques e vendas. Suporta filtros por data, categoria (tag) e busca por nome.
    *   **Resposta**: Dados paginados para a tabela.
*   `GET /api/publicadas`: Endpoint API para dados da tabela (para carregamento assíncrono ou filtros).

#### 5.1.4. Configurações
*   `GET /configuracoes`: Renderiza a tela `Configurações`.
    *   **Dados**: Consulta `lojas_confiaveis`, `tags`, `canais_telegram` e `canal_tags`.

*   **Lojas Confiáveis**:
    *   `POST /api/lojas`: Adiciona nova loja.
    *   `PUT /api/lojas/<id>`: Atualiza loja (nome, pontuação, ativo).
    *   `DELETE /api/lojas/<id>`: Remove loja.

*   **Tags**:
    *   `POST /api/tags`: Adiciona nova tag.
    *   `DELETE /api/tags/<id>`: Remove tag.

*   **Canais Telegram**:
    *   `POST /api/canais`: Adiciona novo canal (com `id_canal_api` e `nome_amigavel`).
    *   `PUT /api/canais/<id>`: Atualiza canal (nome, ativo, associações de tags).
    *   `DELETE /api/canais/<id>`: Remove canal.

### 5.2. Autenticação e Autorização

*   **Autenticação**: Utilizar `Flask-Login` para gerenciar sessões de usuário. Senhas devem ser armazenadas como hashes (ex: `bcrypt`).
*   **Autorização**: Todas as rotas administrativas devem exigir autenticação. Futuramente, pode-se implementar controle de acesso baseado em papéis (RBAC) usando o campo `is_admin` da tabela `usuarios`.

## 6. Segurança

*   **Validação de Entrada**: Todos os dados recebidos do frontend (via formulários ou APIs) devem ser validados e sanitizados no backend para prevenir ataques como SQL Injection e Cross-Site Scripting (XSS).
*   **Hashing de Senhas**: Nunca armazenar senhas em texto puro. Utilizar algoritmos de hashing seguros (ex: `bcrypt`).
*   **CSRF Protection**: Implementar proteção contra Cross-Site Request Forgery (CSRF) para todas as requisições POST, PUT, DELETE.
*   **HTTPS**: Em ambiente de produção, o painel deve ser acessado via HTTPS para criptografar a comunicação.
*   **Controle de Acesso**: Restringir o acesso ao painel administrativo apenas a usuários autorizados.
*   **Logs**: Manter logs detalhados de acesso e ações críticas no sistema para auditoria e depuração.

## 7. Implantação e Operação (Raspberry Pi)

*   **Ambiente Virtual**: Recomenda-se o uso de ambientes virtuais (venv) para isolar as dependências do projeto.
*   **Servidor Web**: Para o Flask, pode-se usar um servidor de desenvolvimento simples (para testes) ou um servidor de produção leve como Gunicorn ou Waitress, com Nginx como proxy reverso para servir arquivos estáticos e gerenciar HTTPS.
*   **Scheduler**: Utilizar `cron` no Raspberry Pi para agendar a execução periódica dos scripts `collector.py`, `validator.py`, `publisher.py` e `metrics_analyzer.py`.
*   **Monitoramento**: Implementar um sistema básico de monitoramento para verificar a saúde dos processos e o uso de recursos do Raspberry Pi.

## 8. Considerações Futuras

*   **Escalabilidade**: Embora o SQLite seja adequado para o início, para um volume muito grande de dados ou múltiplos usuários acessando o painel simultaneamente, a migração para um banco de dados mais robusto (PostgreSQL) pode ser necessária.
*   **Notificações**: Implementar notificações (ex: Telegram) para alertar sobre erros no scraping, ofertas excepcionais ou problemas no sistema.
*   **API do WhatsApp Business**: Quando o projeto escalar e gerar receita, integrar a API oficial do WhatsApp Business para o módulo de publicação.
*   **Geração de Imagens para Instagram**: Integrar APIs de geração/edição de imagens para a Fase 2 do projeto.

---

**Autor**: Manus AI
**Data**: 20 de Agosto de 2025

---

## Referências

[1] Flask Documentation. Disponível em: `https://flask.palletsprojects.com/`
[2] SQLAlchemy Documentation. Disponível em: `https://www.sqlalchemy.org/`
[3] python-telegram-bot Documentation. Disponível em: `https://python-telegram-bot.org/`
[4] Bitly API Documentation. Disponível em: `https://dev.bitly.com/`
[5] Amazon Product Advertising API. Disponível em: `https://developer.amazon.com/paapi5`
[6] Mercado Livre Developers. Disponível em: `https://developers.mercadolivre.com.br/`
[7] SQLite Official Website. Disponível em: `https://www.sqlite.org/`
[8] Bootstrap 5 Documentation. Disponível em: `https://getbootstrap.com/docs/5.3/`
[9] Bcrypt for Python. Disponível em: `https://pypi.org/project/bcrypt/`
[10] Nginx Official Website. Disponível em: `https://nginx.org/`
[11] Gunicorn Documentation. Disponível em: `https://gunicorn.org/`
[12] Waitress Documentation. Disponível em: `https://docs.pylonsproject.org/projects/waitress/en/latest/`
[13] Cron (software). Disponível em: `https://en.wikipedia.org/wiki/Cron`
[14] Alembic Documentation. Disponível em: `https://alembic.sqlalchemy.org/`


## 4. Módulos do Backend e Lógica de Negócio

### 4.1. Módulo de Coleta/Scraping (`collector.py`)

**Responsabilidades:**
*   Buscar novas ofertas nas plataformas de e-commerce configuradas.
*   Atualizar o catálogo de produtos (`produtos`) e o histórico de preços (`historico_precos`).
*   Identificar e inserir novas ofertas na tabela `ofertas` com status `PENDENTE_APROVACAO`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Configurações**: Consulta a tabela `lojas_confiaveis` para identificar quais lojas estão ativas e qual sua pontuação de confiança.
2.  **Iteração por Plataforma/Loja**: Para cada plataforma (Amazon, Mercado Livre):
    *   Utiliza a API oficial (preferencialmente) ou web scraping (se API não disponível ou limitada) para buscar ofertas.
    *   **Amazon**: Utilizar a Product Advertising API (PA-API) [5]. Necessita de credenciais de Associado Amazon. A busca pode ser por categorias, palavras-chave ou listas de produtos.
    *   **Mercado Livre**: Utilizar a API do Mercado Livre [6]. Necessita de credenciais de desenvolvedor. A busca pode ser por termos, categorias e filtros de preço/desconto.
    *   **Web Scraping (Alternativa/Complemento)**: Se APIs não forem suficientes para identificar ofertas com desconto, pode-se implementar web scraping. **Atenção**: Web scraping é frágil e pode ser bloqueado. Deve ser uma alternativa de último recurso e com mecanismos de resiliência (rotação de IPs, user-agents, tratamento de CAPTCHAs).
3.  **Processamento de Produtos Encontrados**:
    *   Para cada produto/oferta encontrada:
        *   Verifica se o `product_id_loja` já existe na tabela `produtos`. Se não, insere um novo registro.
        *   Insere o preço atual na tabela `historico_precos`, associando-o ao `produto_id` e `loja_id`.
        *   **Identificação de Oferta**: Compara o `preco_oferta` com o `preco_original` (se disponível) ou com o `preco` mais recente no `historico_precos` para determinar se é uma oferta válida para consideração.
        *   **Criação de Oferta Pendente**: Se for uma oferta válida, insere um novo registro na tabela `ofertas` com `status = 'PENDENTE_APROVACAO'`, preenchendo `produto_id`, `loja_id`, `preco_original`, `preco_oferta`, `url_afiliado_longa`, `data_encontrado` e `data_validade` (se disponível).
        *   **Categorização Inicial (Tags)**: Baseado no `nome_produto` e/ou categoria fornecida pela API da loja, o módulo deve sugerir tags para o produto. Isso pode ser feito com um dicionário de palavras-chave para tags (ex: "notebook" -> #informatica, "geladeira" -> #eletrodomestico). As tags sugeridas são armazenadas na tabela `produto_tags`.

### 4.2. Módulo de Validação de Ofertas (`validator.py`)

**Responsabilidades:**
*   Aplicar regras de negócio para qualificar as ofertas `PENDENTE_APROVACAO`.
*   Atualizar o `status` da oferta para `APROVADO` ou `REJEITADO` e preencher o `motivo_validacao`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Ofertas Pendentes**: Consulta a tabela `ofertas` por registros com `status = 'PENDENTE_APROVACAO'`.
2.  **Iteração por Oferta**:
    *   **Verificação de Desconto Real (Baseado no Histórico Próprio)**:
        *   Consulta a tabela `historico_precos` para o `produto_id` da oferta.
        *   Calcula o menor preço e o preço médio dos últimos 30, 60 e 90 dias (conforme regras de negócio).
        *   **Regra**: Se `preco_oferta` for o menor preço dos últimos 60 dias OU `preco_oferta` for X% (ex: 10%) menor que o preço médio dos últimos 30 dias, a oferta é pré-aprovada.
        *   Preenche o `motivo_validacao` (ex: "Menor preço dos últimos 90 dias", "X% abaixo da média").
    *   **Comparação com Comparadores Externos (Opcional/Secundário)**:
        *   **Atenção**: Esta etapa é de ALTO RISCO e FRAGILIDADE devido ao web scraping. Deve ser implementada com cautela.
        *   Para produtos da Amazon, tenta buscar o histórico no CamelCamelCamel. Para outros, no Zoom.
        *   Se dados confiáveis forem obtidos, eles podem ser usados para reforçar a validação ou como um critério adicional.
        *   Os dados obtidos são armazenados na tabela `verificacao_precos` (se implementada).
    *   **Regra de Duplicidade/Melhor Preço**: Verifica se o mesmo `product_id_loja` (ou um identificador similar) já existe em outra oferta `PENDENTE_APROVACAO` ou `APROVADO` com um preço menor. Se sim, a oferta atual é marcada como `REJEITADO`.
    *   **Atualização de Status**: Se a oferta passar por todas as regras de validação, seu `status` é atualizado para `APROVADO` (se a curadoria for totalmente automática) ou permanece `PENDENTE_APROVACAO` (se for para revisão humana no painel, que é o caso atual). O `motivo_validacao` é atualizado.

### 4.3. Módulo de Publicação de Ofertas (`publisher.py`)

**Responsabilidades:**
*   Processar ofertas com `status = 'APROVADO'` ou `AGENDADO`.
*   Encurtar URLs de afiliado via Bitly.
*   Formatar mensagens e publicá-las nos canais do Telegram.
*   Atualizar o status da oferta para `PUBLICADO`.

**Fluxo de Execução (via Scheduler ou acionado pelo Painel Web):**
1.  **Leitura de Ofertas Aprovadas/Agendadas**: Consulta a tabela `ofertas` por registros com `status = 'APROVADO'` ou `AGENDADO` (e `data_publicacao` <= data/hora atual para agendados).
2.  **Iteração por Oferta**:
    *   **Encurtamento de URL**: Se `url_afiliado_curta` estiver vazio, chama a API do Bitly [4] para encurtar `url_afiliado_longa`. Armazena o link curto e o `link_id` do Bitly (para métricas) na tabela `ofertas`.
    *   **Determinação de Canais de Destino**: 
        *   Consulta a tabela `produto_tags` para obter as tags do produto.
        *   Consulta a tabela `canal_tags` para encontrar todos os `canais_telegram` ativos que estão associados a pelo menos uma das tags do produto.
    *   **Formatação da Mensagem**: Constrói a mensagem a ser enviada para o Telegram, incluindo:
        *   Nome do produto.
        *   Preço da oferta e, opcionalmente, preço original riscado.
        *   `motivo_validacao` (ex: "Menor preço dos últimos 90 dias").
        *   URL encurtada do Bitly.
        *   Emojis e formatação para chamar a atenção.
    *   **Publicação no Telegram**: Utiliza a API do Bot do Telegram [3] para enviar a mensagem para cada `id_canal_api` determinado.
        *   **Tratamento de Erros**: Implementar retry logic para falhas temporárias da API do Telegram.
        *   Armazena o `mensagem_id_telegram` retornado pela API na tabela `ofertas`.
    *   **Atualização de Status**: Atualiza o `status` da oferta para `PUBLICADO` e `data_publicacao` na tabela `ofertas`.

### 4.4. Módulo de Análise de Métricas (`metrics_analyzer.py`)

**Responsabilidades:**
*   Coletar dados de cliques do Bitly.
*   Coletar dados de vendas das plataformas de afiliados.
*   Atualizar a tabela `metricas_ofertas`.

**Fluxo de Execução (via Scheduler):**
1.  **Leitura de Ofertas Publicadas**: Consulta a tabela `ofertas` por registros com `status = 'PUBLICADO'`.
2.  **Iteração por Oferta Publicada**:
    *   **Coleta de Cliques (Bitly)**: Utiliza a API do Bitly [4] para obter o número de cliques para a `url_afiliado_curta` (usando o `link_id` do Bitly).
    *   **Coleta de Vendas (APIs de Afiliados)**: 
        *   **Amazon/Mercado Livre**: A forma mais confiável é através dos relatórios de vendas das APIs de afiliados, usando os `Tracking IDs` ou `Sub-IDs` que foram gerados na `url_afiliado_longa`.
        *   **Desafio**: A obtenção de dados de vendas via API pode ser complexa e nem sempre em tempo real. Pode ser necessário um processo semi-manual de importação de relatórios em CSV para o banco de dados, especialmente no início.
    *   **Atualização de Métricas**: Atualiza ou insere um registro na tabela `metricas_ofertas` com os `cliques`, `vendas` e `data_atualizacao`.

## 5. Painel Administrativo Web (Flask)

O painel web será a interface para o usuário interagir com o sistema. Ele será construído com Flask [1] e interagirá com o banco de dados SQLite [7].

### 5.1. Rotas e Endpoints da API

#### 5.1.1. Autenticação
*   `GET /login`: Renderiza a tela de login.
*   `POST /login`: Autentica o usuário. Se sucesso, redireciona para `/dashboard`. Se falha, exibe erro.
*   `GET /logout`: Desloga o usuário e redireciona para `/login`.

#### 5.1.2. Fila de Aprovação (Tela Principal)
*   `GET /dashboard` ou `GET /`: Renderiza a tela `Fila de Aprovação`.
    *   **Dados**: Consulta a tabela `ofertas` por `status = 'PENDENTE_APROVACAO'`. Retorna todos os dados necessários para renderizar os cards (nome, imagem, preços, motivo validação, tags sugeridas, canais de destino).
*   `POST /ofertas/<id>/aprovar`: 
    *   **Parâmetros**: `id` da oferta, `tags` (lista de strings).
    *   **Ação**: Atualiza as tags do produto (`produto_tags`). Atualiza o `status` da oferta para `APROVADO` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.
*   `POST /ofertas/<id>/rejeitar`: 
    *   **Parâmetros**: `id` da oferta.
    *   **Ação**: Atualiza o `status` da oferta para `REJEITADO` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.
*   `POST /ofertas/<id>/agendar`: 
    *   **Parâmetros**: `id` da oferta, `data_agendamento` (datetime).
    *   **Ação**: Atualiza o `status` da oferta para `AGENDADO` e define `data_publicacao` na tabela `ofertas`.
    *   **Resposta**: JSON de sucesso/erro.

#### 5.1.3. Ofertas Publicadas
*   `GET /publicadas`: Renderiza a tela `Ofertas Publicadas`.
    *   **Dados**: Consulta a tabela `ofertas` por `status = 'PUBLICADO'`. Realiza JOIN com `metricas_ofertas` para obter cliques e vendas. Suporta filtros por data, categoria (tag) e busca por nome.
    *   **Resposta**: Dados paginados para a tabela.
*   `GET /api/publicadas`: Endpoint API para dados da tabela (para carregamento assíncrono ou filtros).

#### 5.1.4. Configurações
*   `GET /configuracoes`: Renderiza a tela `Configurações`.
    *   **Dados**: Consulta `lojas_confiaveis`, `tags`, `canais_telegram` e `canal_tags`.

*   **Lojas Confiáveis**:
    *   `POST /api/lojas`: Adiciona nova loja.
    *   `PUT /api/lojas/<id>`: Atualiza loja (nome, pontuação, ativo).
    *   `DELETE /api/lojas/<id>`: Remove loja.

*   **Tags**:
    *   `POST /api/tags`: Adiciona nova tag.
    *   `DELETE /api/tags/<id>`: Remove tag.

*   **Canais Telegram**:
    *   `POST /api/canais`: Adiciona novo canal (com `id_canal_api` e `nome_amigavel`).
    *   `PUT /api/canais/<id>`: Atualiza canal (nome, ativo, associações de tags).
    *   `DELETE /api/canais/<id>`: Remove canal.

### 5.2. Autenticação e Autorização

*   **Autenticação**: Utilizar `Flask-Login` para gerenciar sessões de usuário. Senhas devem ser armazenadas como hashes (ex: `bcrypt`) [9].
*   **Autorização**: Todas as rotas administrativas devem exigir autenticação. Futuramente, pode-se implementar controle de acesso baseado em papéis (RBAC) usando o campo `is_admin` da tabela `usuarios`.

## 6. Segurança

*   **Validação de Entrada**: Todos os dados recebidos do frontend (via formulários ou APIs) devem ser validados e sanitizados no backend para prevenir ataques como SQL Injection e Cross-Site Scripting (XSS).
*   **Hashing de Senhas**: Nunca armazenar senhas em texto puro. Utilizar algoritmos de hashing seguros (ex: `bcrypt`).
*   **CSRF Protection**: Implementar proteção contra Cross-Site Request Forgery (CSRF) para todas as requisições POST, PUT, DELETE.
*   **HTTPS**: Em ambiente de produção, o painel deve ser acessado via HTTPS para criptografar a comunicação.
*   **Controle de Acesso**: Restringir o acesso ao painel administrativo apenas a usuários autorizados.
*   **Logs**: Manter logs detalhados de acesso e ações críticas no sistema para auditoria e depuração.

## 7. Implantação e Operação (Raspberry Pi)

*   **Ambiente Virtual**: Recomenda-se o uso de ambientes virtuais (venv) para isolar as dependências do projeto.
*   **Servidor Web**: Para o Flask, pode-se usar um servidor de desenvolvimento simples (para testes) ou um servidor de produção leve como Gunicorn [11] ou Waitress [12], com Nginx [10] como proxy reverso para servir arquivos estáticos e gerenciar HTTPS.
*   **Scheduler**: Utilizar `cron` [13] no Raspberry Pi para agendar a execução periódica dos scripts `collector.py`, `validator.py`, `publisher.py` e `metrics_analyzer.py`.
*   **Monitoramento**: Implementar um sistema básico de monitoramento para verificar a saúde dos processos e o uso de recursos do Raspberry Pi.

## 8. Considerações Futuras

*   **Escalabilidade**: Embora o SQLite seja adequado para o início, para um volume muito grande de dados ou múltiplos usuários acessando o painel simultaneamente, a migração para um banco de dados mais robusto (PostgreSQL) pode ser necessária.
*   **Notificações**: Implementar notificações (ex: Telegram) para alertar sobre erros no scraping, ofertas excepcionais ou problemas no sistema.
*   **API do WhatsApp Business**: Quando o projeto escalar e gerar receita, integrar a API oficial do WhatsApp Business para o módulo de publicação.
*   **Geração de Imagens para Instagram**: Integrar APIs de geração/edição de imagens para a Fase 2 do projeto.

---

**Autor**: Manus AI
**Data**: 20 de Agosto de 2025

---

## Referências

[1] Flask Documentation. Disponível em: `https://flask.palletsprojects.com/`
[2] SQLAlchemy Documentation. Disponível em: `https://www.sqlalchemy.org/`
[3] python-telegram-bot Documentation. Disponível em: `https://python-telegram-bot.org/`
[4] Bitly API Documentation. Disponível em: `https://dev.bitly.com/`
[5] Amazon Product Advertising API. Disponível em: `https://developer.amazon.com/paapi5`
[6] Mercado Livre Developers. Disponível em: `https://developers.mercadolivre.com.br/`
[7] SQLite Official Website. Disponível em: `https://www.sqlite.org/`
[8] Bootstrap 5 Documentation. Disponível em: `https://getbootstrap.com/docs/5.3/`
[9] Bcrypt for Python. Disponível em: `https://pypi.org/project/bcrypt/`
[10] Nginx Official Website. Disponível em: `https://nginx.org/`
[11] Gunicorn Documentation. Disponível em: `https://gunicorn.org/`
[12] Waitress Documentation. Disponível em: `https://docs.pylonsproject.org/projects/waitress/en/latest/`
[13] Cron (software). Disponível em: `https://en.wikipedia.org/wiki/Cron`
[14] Alembic Documentation. Disponível em: `https://alembic.sqlalchemy.org/`

