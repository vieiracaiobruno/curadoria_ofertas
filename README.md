# Sistema de Curadoria de Ofertas

Um sistema automatizado completo para coleta, validação e publicação de ofertas do Mercado Livre e Amazon em canais do Telegram, com painel web de gerenciamento.

## 🚀 Funcionalidades Principais

- **Coleta Automatizada de Ofertas**
  - 🌐 Modo HTTP direto (rápido e leve, sem dependências de navegador)
  - 🎯 Modo Selenium (completo, com suporte a JavaScript)
  - 🔄 Coleta configurável por páginas e delays
  - 🧵 Enriquecimento paralelo com múltiplos workers
  
- **Processamento Inteligente**
  - 📊 Detecção automática de descontos e ofertas
  - 🏷️ Sistema de tags para categorização
  - 🔍 Validação baseada em critérios configuráveis
  - 📦 Persistência em banco de dados SQLite
  
- **Publicação Automatizada**
  - 📱 Envio para múltiplos canais do Telegram
  - 🎨 Formatação automática de mensagens em MarkdownV2
  - ⏰ Agendamento de publicações
  - 📈 Rastreamento de métricas por canal
  
- **Painel Web de Controle**
  - 🖥️ Interface Bootstrap responsiva
  - ✅ Aprovação/rejeição manual de ofertas
  - ⚙️ Gerenciamento de lojas, tags e canais
  - 📊 Visualização de produtos e histórico de publicações
  - 📝 Consulta de logs de coleta

## 📁 Estrutura do Projeto

```
curadoria_ofertas/
├── app.py                              # Aplicação principal Flask
├── run_pipeline.py                     # Pipeline completo de curadoria
├── requirements.txt                    # Dependências Python
├── config.env                          # Configurações (criar manualmente)
├── setup_cron.sh                       # Script para configurar cron job
├── copilot-instructions.md            # Instruções para desenvolvimento
│
├── backend/                            # Código backend
│   ├── db/
│   │   ├── database.py                # Configuração do banco de dados
│   │   └── curadoria_ofertas.db       # Banco SQLite (criado automaticamente)
│   │
│   ├── models/
│   │   └── models.py                  # Modelos SQLAlchemy (Produto, Oferta, etc.)
│   │
│   ├── modules/
│   │   ├── collectors/
│   │   │   ├── base.py                # Classe base para coletores
│   │   │   ├── ml_collector.py        # Coletor do Mercado Livre
│   │   │   └── amazon_collector.py    # Coletor da Amazon
│   │   │
│   │   ├── services/
│   │   │   └── offer_processor.py     # Processamento de ofertas
│   │   │
│   │   ├── utils/
│   │   │   ├── config.py              # Gerenciamento de configurações
│   │   │   ├── selenium_client.py     # Cliente Selenium reutilizável
│   │   │   └── cookie_utils.py        # Gerenciamento de cookies
│   │   │
│   │   ├── validator.py               # Validação de ofertas
│   │   ├── publisher.py               # Publicação no Telegram
│   │   └── metrics_analyzer.py        # Análise de métricas
│   │
│   ├── routes/
│   │   └── api.py                     # Rotas da API REST
│   │
│   └── http/
│       └── browser_client.py          # Cliente HTTP para scraping
│
├── frontend/                           # Interface web
│   ├── templates/                     # Templates Jinja2
│   │   ├── fila_aprovacao.html       # Dashboard de aprovação
│   │   ├── ofertas_publicadas.html   # Histórico de publicações
│   │   ├── produtos.html             # Lista de produtos
│   │   ├── configuracoes.html        # Gerenciamento de tags/canais
│   │   ├── lojas_confiaveis.html     # Gerenciamento de lojas
│   │   ├── logs_coleta.html          # Visualização de logs
│   │   └── env_vars.html             # Variáveis de ambiente
│   │
│   └── static/                        # Arquivos estáticos (CSS, JS)
│
└── scripts/                            # Scripts utilitários
    ├── iniciar_scrapper_ml.py         # Script de coleta standalone (ML)
    ├── iniciar_scrapper_amazon.py     # Script de coleta standalone (Amazon)
    └── iniciar_tabela_com_var.py      # Script de inicialização de dados
```

## 🛠️ Instalação

### Pré-requisitos
- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)
- Chrome/Chromium instalado (opcional, apenas se usar modo Selenium)

### Passos de Instalação

1. **Clone o repositório**
   ```bash
   git clone https://github.com/vieiracaiobruno/curadoria_ofertas.git
   cd curadoria_ofertas
   ```

2. **Crie um ambiente virtual (recomendado)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # ou
   venv\Scripts\activate     # Windows
   ```

3. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure as variáveis de ambiente**
   
   Crie um arquivo `config.env` na raiz do projeto com as seguintes configurações:
   
   ```env
   # Database Configuration
   DATABASE_URL=sqlite:///./backend/db/curadoria_ofertas.db
   
   # Flask Configuration
   SECRET_KEY=sua-chave-secreta-aqui
   FLASK_ENV=development
   FLASK_DEBUG=True
   PORT=5000
   
   # Admin Configuration (opcional)
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=sua-senha-aqui
   ADMIN_EMAIL=admin@example.com
   
   # Telegram Configuration
   TELEGRAM_BOT_TOKEN=seu-token-do-bot
   TELEGRAM_CHANNEL_ID=@seu_canal
   
   # Mercado Livre Collector Configuration
   ENABLE_ML_COLLECTOR=true        # Habilita/desabilita coleta do ML
   USE_SELENIUM=false              # true = Selenium, false = HTTP (mais rápido)
   ML_MAX_PAGES=3                  # Número de páginas para coletar
   ML_REQUEST_DELAY_SEC=2          # Delay entre requisições (segundos)
   ML_ENRICH_WORKERS=1             # Workers paralelos para enriquecimento
   
   # Amazon Collector Configuration
   ENABLE_AMAZON_COLLECTOR=false   # Habilita/desabilita coleta da Amazon
   AMAZON_MAX_PAGES=3              # Número de páginas para coletar
   AMAZON_REQUEST_DELAY_SEC=2      # Delay entre requisições (segundos)
   
   # Logging Configuration (opcional)
   LOG_FILE=./logs/pipeline.log
   RESULTS_FILE=./logs/pipeline_results.json
   ```

5. **Inicialize o banco de dados**
   
   O banco de dados será criado automaticamente na primeira execução, mas você pode forçar a criação:
   ```bash
   python -c "from backend.db.database import create_db_tables; create_db_tables()"
   ```

6. **Execute a aplicação**
   ```bash
   python app.py
   ```

7. **Acesse o painel web**
   - URL: http://localhost:5000
   - Configure lojas, tags e canais antes de executar o pipeline

## ⚙️ Configuração

### Modos de Coleta: Selenium vs HTTP

O sistema suporta dois modos de coleta do Mercado Livre, configurável via `USE_SELENIUM`:

#### 🌐 Modo HTTP (Recomendado - `USE_SELENIUM=false`)
- ✅ **5x mais rápido** que Selenium
- ✅ **10x menos memória**
- ✅ Não requer Chrome/navegador instalado
- ✅ Mais difícil de ser detectado como bot
- ✅ Ideal para servidores e ambientes de produção
- ⚠️ Não extrai alguns campos avançados (ganho_real, url_afiliado_curta)

#### 🎯 Modo Selenium (`USE_SELENIUM=true`)
- ✅ Extrai **todos os campos** incluindo ganho_real e url_afiliado_curta
- ✅ Suporta JavaScript e conteúdo dinâmico
- ✅ Simula comportamento de navegador real
- ⚠️ Mais lento e consome mais recursos
- ⚠️ Requer Chrome/Chromium instalado
- ⚠️ Pode ser detectado como bot em algumas situações

**Recomendação**: Use modo HTTP para coletas frequentes e produção. Use Selenium apenas se precisar dos campos extras.

### Configuração de Coletores

O sistema suporta múltiplos coletores que podem ser habilitados/desabilitados individualmente:

#### 🛒 Coletor do Mercado Livre
- **Habilitado por padrão** (`ENABLE_ML_COLLECTOR=true`)
- Suporta modo HTTP e Selenium
- Configurações: `ML_MAX_PAGES`, `ML_REQUEST_DELAY_SEC`, `ML_ENRICH_WORKERS`

#### 📦 Coletor da Amazon
- **Desabilitado por padrão** (`ENABLE_AMAZON_COLLECTOR=false`)
- Usa apenas modo HTTP (mais rápido e confiável)
- Configurações: `AMAZON_MAX_PAGES`, `AMAZON_REQUEST_DELAY_SEC`
- **Como habilitar**:
  1. No arquivo `config.env`, defina `ENABLE_AMAZON_COLLECTOR=true`
  2. Configure o número de páginas: `AMAZON_MAX_PAGES=3`
  3. Execute o pipeline normalmente: `python run_pipeline.py`

**Nota**: Para testar apenas o coletor da Amazon, use o script standalone:
```bash
python scripts/iniciar_scrapper_amazon.py
```

### Configuração do Telegram

Para habilitar a publicação automática no Telegram:

1. **Crie um bot**
   - Abra o Telegram e busque por `@BotFather`
   - Envie `/newbot` e siga as instruções
   - Copie o token fornecido

2. **Configure o canal**
   - Crie um canal no Telegram ou use um existente
   - Adicione seu bot como administrador do canal
   - Obtenha o ID do canal (formato: `@nome_do_canal` ou `-100XXXXXXXXX`)

3. **Configure no sistema**
   - Adicione o token e ID do canal no `config.env`
   - Cadastre o canal no painel web (Configurações > Canais)
   - Associe tags ao canal para filtragem automática

### Configuração de Lojas Confiáveis

1. Acesse o painel web em **Lojas Confiáveis**
2. Adicione novas lojas informando:
   - Nome da loja
   - Plataforma (Mercado Livre)
   - ID da loja na API (seller_id)
   - Pontuação de confiança (1-5)
   - Status (ativa/inativa)

### Sistema de Tags

Tags são usadas para categorizar produtos e direcionar ofertas para canais específicos:

1. Acesse **Configurações** no painel web
2. Adicione tags relevantes (ex: "eletrônicos", "casa", "games")
3. Associe tags aos canais do Telegram
4. O sistema detecta automaticamente tags no nome dos produtos

## 🚀 Uso

### Painel Web

O painel web oferece interface completa para gerenciamento:

```bash
python app.py
```

Acesse http://localhost:5000 e navegue pelas seções:

- **Dashboard**: Fila de aprovação de ofertas pendentes
- **Publicadas**: Histórico de ofertas publicadas
- **Produtos**: Lista completa de produtos coletados
- **Lojas Confiáveis**: Gerenciar lojas para coleta
- **Configurações**: Gerenciar tags e canais do Telegram
- **Logs**: Visualizar logs de coleta e erros
- **Variáveis**: Consultar variáveis de ambiente

### Execução do Pipeline

#### Manual (Linha de Comando)

Execute o pipeline completo de curadoria:

```bash
python run_pipeline.py
```

O pipeline executa as seguintes etapas:
1. **Coleta**: Busca ofertas do Mercado Livre
2. **Processamento**: Estrutura e persiste dados no banco
3. **Validação**: Aplica regras de validação configuráveis
4. **Publicação**: Envia ofertas aprovadas para Telegram
5. **Métricas**: Analisa performance das publicações

#### Automatizada (Cron Job)

Para execução periódica automática, use o script `setup_cron.sh`:

```bash
# Torne o script executável
chmod +x setup_cron.sh

# Execute o script (irá configurar cron job)
./setup_cron.sh
```

Ou configure manualmente:

```bash
# Edite o crontab
crontab -e

# Adicione a linha (executa a cada 2 horas)
0 */2 * * * cd /caminho/para/curadoria_ofertas && /caminho/para/venv/bin/python run_pipeline.py >> logs/cron.log 2>&1
```

### Scripts Auxiliares

```bash
# Coleta standalone do Mercado Livre
python scripts/iniciar_scrapper_ml.py

# Inicialização de dados de teste
python scripts/iniciar_tabela_com_var.py
```

## 🔌 API REST

O sistema expõe uma API REST para integração e automação:

### Endpoints de Ofertas

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/canais_destino?tags=tag1,tag2` | Busca canais por tags |
| `POST` | `/api/ofertas/{id}/aprovar` | Aprova uma oferta pendente |
| `POST` | `/api/ofertas/{id}/rejeitar` | Rejeita uma oferta |
| `POST` | `/api/ofertas/{id}/agendar` | Agenda publicação de oferta |

### Endpoints de Lojas

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/lojas` | Adiciona nova loja confiável |
| `PUT` | `/api/lojas/{id}` | Atualiza dados de uma loja |
| `DELETE` | `/api/lojas/{id}` | Remove uma loja |
| `PATCH` | `/api/lojas/{id}/toggle` | Ativa/desativa uma loja |

### Endpoints de Tags

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/tags` | Adiciona nova tag |
| `DELETE` | `/api/tags/{id}` | Remove uma tag |

### Endpoints de Canais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/canais` | Adiciona novo canal Telegram |
| `PUT` | `/api/canais/{id}` | Atualiza dados de um canal |
| `DELETE` | `/api/canais/{id}` | Remove um canal |

### Exemplos de Uso

```bash
# Aprovar uma oferta
curl -X POST http://localhost:5000/api/ofertas/123/aprovar

# Adicionar uma tag
curl -X POST http://localhost:5000/api/tags \
  -H "Content-Type: application/json" \
  -d '{"nome_tag": "eletrônicos"}'

# Buscar canais por tags
curl http://localhost:5000/api/canais_destino?tags=eletrônicos,promoção
```

## 💾 Modelo de Dados

O sistema utiliza SQLAlchemy com as seguintes entidades principais:

### Entidades Core

- **`Produto`**: Produtos coletados com informações base
  - Campos: id, id_product, nome_produto, url_base, imagem_url, preco_original, preco_oferta
  - Relacionamentos: tags (N:N), ofertas (1:N), historico_precos (1:N)

- **`Oferta`**: Instâncias de ofertas de produtos
  - Campos: id, produto_id, loja_id, desconto_percentual, status, data_coleta
  - Status possíveis: PENDENTE_APROVACAO, APROVADO, REJEITADO, PUBLICADO
  - Relacionamentos: produto (N:1), loja (N:1)

- **`LojaConfiavel`**: Lojas cadastradas para coleta
  - Campos: id, nome_loja, plataforma, id_loja_api, pontuacao_confianca, ativa
  - Relacionamentos: ofertas (1:N), historico_precos (1:N)

- **`Tag`**: Tags para categorização
  - Campos: id, nome_tag
  - Relacionamentos: produtos (N:N), canais (N:N)

- **`CanalTelegram`**: Canais de publicação
  - Campos: id, id_canal_api, nome_amigavel, ativo, inscritos
  - Relacionamentos: tags (N:N), ofertas_publicadas (1:N)

### Entidades Auxiliares

- **`OfertaPublicada`**: Registro de publicações realizadas
- **`MetricaOferta`**: Métricas de cliques e conversões
- **`HistoricoPreco`**: Histórico de variações de preço
- **`LogColeta`**: Logs de execução do pipeline

## 🔧 Desenvolvimento

### Ambiente de Desenvolvimento

```bash
# Ativar ambiente virtual
source venv/bin/activate

# Instalar dependências de desenvolvimento
pip install -r requirements.txt

# Configurar variáveis para desenvolvimento
export FLASK_ENV=development
export FLASK_DEBUG=True
```

### Estrutura de Módulos

- **Collectors** (`backend/modules/collectors/`): Implementam coleta de dados
  - `BaseCollector`: Classe abstrata base
  - `MLCollector`: Implementação para Mercado Livre
  - `AmazonCollector`: Implementação para Amazon Brasil

- **Services** (`backend/modules/services/`): Lógica de negócio
  - `OfferProcessor`: Processa e persiste ofertas

- **Utils** (`backend/modules/utils/`): Utilitários
  - `config.py`: Gerenciamento de configurações
  - `selenium_client.py`: Cliente Selenium reutilizável
  - `cookie_utils.py`: Gerenciamento de cookies para múltiplos sites

### Adicionando Novos Coletores

Para adicionar suporte a uma nova plataforma:

1. Crie uma classe herdando de `BaseCollector` em `backend/modules/collectors/`
2. Implemente os métodos abstratos:
   - `collect()`: Lógica de coleta
   - `parse_item()`: Parse de dados
   - `enrich_item()`: Enriquecimento de dados
3. Registre a loja no banco via painel web
4. Configure tags apropriadas para categorização

### Padrões de Código

- Use type hints para melhor documentação
- Docstrings em português para funções públicas
- Logs claros em etapas críticas
- Tratamento robusto de exceções
- Testes unitários para lógica complexa

## 🐛 Troubleshooting

### Problemas Comuns e Soluções

#### Erro: ModuleNotFoundError ou ImportError
```bash
# Certifique-se de estar no diretório correto
cd curadoria_ofertas

# E que o ambiente virtual está ativado
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Reinstale as dependências se necessário
pip install -r requirements.txt
```

#### Erro: Banco de dados não encontrado
```bash
# Recrie as tabelas do banco
python -c "from backend.db.database import create_db_tables; create_db_tables()"
```

#### Erro: Telegram bot não consegue publicar
1. Verifique se o token está correto no `config.env`
2. Confirme que o bot foi adicionado ao canal como **administrador**
3. Verifique o ID do canal (formato: `@nome_canal` ou `-100XXXXXXXXX`)
4. Teste o bot enviando `/start` diretamente

#### Erro: Permission denied ao criar logs
```bash
# Crie o diretório de logs manualmente
mkdir -p logs
chmod 755 logs
```

#### Problema: Coleta muito lenta
- Use modo HTTP: defina `USE_SELENIUM=false` no `config.env`
- Reduza o número de páginas: `ML_MAX_PAGES=2`
- Diminua workers paralelos: `ML_ENRICH_WORKERS=1`

#### Problema: Chrome não instalado
```bash
# Solução 1: Use modo HTTP (recomendado)
# No config.env: USE_SELENIUM=false

# Solução 2: Instale o Chrome/Chromium
# Ubuntu/Debian:
sudo apt-get install chromium-browser

# Fedora:
sudo dnf install chromium
```

#### Problema: Ofertas não aparecem no dashboard
1. Verifique se o pipeline foi executado: `python run_pipeline.py`
2. Consulte os logs: `/logs` no painel web ou `tail -f logs/pipeline.log`
3. Verifique se há lojas cadastradas e ativas no painel

### Logs e Monitoramento

#### Localização dos Logs

- **Pipeline**: `./logs/pipeline.log` - Logs detalhados de execução
- **Resultados**: `./logs/pipeline_results.json` - Métricas de cada execução
- **Cron**: `./logs/cron.log` - Saída do cron job (se configurado)

#### Visualização de Logs

```bash
# Ver logs em tempo real
tail -f logs/pipeline.log

# Ver últimas 100 linhas
tail -n 100 logs/pipeline.log

# Buscar erros específicos
grep ERROR logs/pipeline.log
```

#### Logs no Painel Web

Acesse http://localhost:5000/logs para visualizar:
- Histórico de coletas
- Erros e warnings
- Timestamps convertidos para fuso horário local

## 📊 Tecnologias Utilizadas

- **Backend**: Python 3.8+, Flask 2.3
- **Banco de Dados**: SQLite com SQLAlchemy 2.0
- **Web Scraping**: BeautifulSoup 4, Selenium 4, httpx
- **Frontend**: Jinja2, Bootstrap 5
- **Integração**: Telegram Bot API
- **Configuração**: python-dotenv

## 🤝 Contribuição

Contribuições são bem-vindas! Para contribuir:

1. **Fork** o projeto
2. Crie uma **branch** para sua feature (`git checkout -b feature/MinhaFeature`)
3. **Commit** suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. **Push** para a branch (`git push origin feature/MinhaFeature`)
5. Abra um **Pull Request**

### Diretrizes de Contribuição

- Siga os padrões de código definidos em `copilot-instructions.md`
- Adicione testes para novas funcionalidades
- Atualize a documentação conforme necessário
- Use mensagens de commit descritivas
- Mantenha compatibilidade com Python 3.8+

## 📝 Roadmap

- [x] Suporte à Amazon Brasil
- [ ] Suporte a mais plataformas (AliExpress, Shopee)
- [ ] Dashboard de métricas avançadas
- [ ] Sistema de notificações por email
- [ ] API GraphQL para consultas complexas
- [ ] Containerização com Docker
- [ ] Testes automatizados (pytest)
- [ ] CI/CD com GitHub Actions
- [ ] Suporte a múltiplos idiomas

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 👥 Autores

- **Caio Bruno Vieira** - [@vieiracaiobruno](https://github.com/vieiracaiobruno)

## 🙏 Agradecimentos

- Comunidade Python Brasil
- Documentação do Flask e SQLAlchemy
- Telegram Bot API
- Mercado Livre (dados públicos)
