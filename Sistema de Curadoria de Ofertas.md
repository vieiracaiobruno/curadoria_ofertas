# Sistema de Curadoria de Ofertas

Sistema automatizado para coleta, validação e publicação de ofertas de produtos da Amazon e Mercado Livre em canais do Telegram, com painel web para gestão e curadoria.

## Características Principais

- **Coleta Automatizada**: Busca ofertas em Amazon e Mercado Livre
- **Validação Inteligente**: Verifica descontos reais baseado em histórico de preços
- **Sistema de Tags**: Categorização flexível por tags (informática, gamer, casa, etc.)
- **Painel Web**: Interface completa para aprovação, rejeição e agendamento de ofertas
- **Métricas**: Acompanhamento de cliques e vendas via Bitly e APIs de afiliados
- **Publicação Automática**: Envio para canais Telegram baseado em tags
- **Scheduler**: Execução automática via cron jobs

## Estrutura do Projeto

```
curadoria_ofertas/
├── backend/
│   ├── db/
│   │   ├── database.py          # Configuração do banco SQLite
│   │   └── curadoria_ofertas.db # Banco de dados SQLite
│   ├── models/
│   │   └── models.py            # Modelos SQLAlchemy
│   ├── modules/
│   │   ├── collector.py         # Módulo de coleta de ofertas
│   │   ├── validator.py         # Módulo de validação
│   │   ├── publisher.py         # Módulo de publicação no Telegram
│   │   └── metrics_analyzer.py  # Módulo de análise de métricas
│   ├── routes/
│   │   └── api.py              # Rotas da API REST
│   └── utils/
│       └── auth.py             # Utilitários de autenticação
├── frontend/
│   ├── templates/              # Templates HTML
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── fila_aprovacao.html
│   │   ├── ofertas_publicadas.html
│   │   └── configuracoes.html
│   └── static/                 # Arquivos estáticos
│       └── placeholder.png
├── app.py                      # Aplicação Flask principal
├── run_pipeline.py             # Script do pipeline completo
├── setup_cron.sh              # Script para configurar cron jobs
└── README.md                  # Este arquivo
```

## Instalação

### 1. Pré-requisitos

- Python 3.11+
- SQLite3
- Acesso à internet

### 2. Configuração do Ambiente

```bash
# Clone ou copie o projeto para o diretório desejado
cd /home/ubuntu/curadoria_ofertas

# Crie e ative o ambiente virtual
python3.11 -m venv venv
python -m venv venv (windows)
source venv/bin/activate
venv\Scripts\activate (windows)

# Instale as dependências
pip install Flask Flask-Login SQLAlchemy python-telegram-bot requests beautifulsoup4 bcrypt python-dotenv
```

### 3. Configuração do Banco de Dados

```bash
# Crie as tabelas do banco de dados
python3.11 backend/db/database.py
```

### 4. Configuração de APIs

Edite os arquivos de módulos e configure seus tokens:

**backend/modules/publisher.py:**
```python
TELEGRAM_BOT_TOKEN = "SEU_TOKEN_DO_BOT_TELEGRAM"
BITLY_ACCESS_TOKEN = "SEU_TOKEN_DO_BITLY"
```

**backend/modules/metrics_analyzer.py:**
```python
BITLY_ACCESS_TOKEN = "SEU_TOKEN_DO_BITLY"
```

### 5. Configuração do Cron (Opcional)

```bash
# Configure a execução automática a cada 2 horas
./setup_cron.sh
```

## Uso

### 1. Iniciando o Painel Web

```bash
# Ative o ambiente virtual
source venv/bin/activate

# Inicie a aplicação Flask
python3.11 app.py
```

A aplicação estará disponível em: http://localhost:5000

**Credenciais padrão:**
- Usuário: `admin`
- Senha: `admin_password`

### 2. Executando o Pipeline Manualmente

```bash
# Execute o pipeline completo uma vez
python3.11 run_pipeline.py
```

### 3. Usando o Painel Web

1. **Login**: Acesse com as credenciais padrão
2. **Configurações**: Configure lojas confiáveis, tags e canais Telegram
3. **Fila de Aprovação**: Revise, aprove, rejeite ou agende ofertas
4. **Ofertas Publicadas**: Acompanhe métricas de desempenho

## Funcionalidades Detalhadas

### Coleta de Ofertas
- Busca automática em lojas configuradas
- Sugestão automática de tags baseada em palavras-chave
- Registro de histórico de preços

### Validação
- Verificação de desconto real (mínimo 10%)
- Eliminação de duplicatas
- Priorização do menor preço por produto

### Publicação
- Encurtamento de URLs via Bitly
- Formatação automática de mensagens
- Distribuição baseada em tags dos produtos

### Métricas
- Rastreamento de cliques via Bitly
- Simulação de vendas (integração real requer APIs de afiliados)
- Cálculo de taxa de conversão

## Configuração de Tokens

### Bot do Telegram
1. Crie um bot via @BotFather
2. Obtenha o token do bot
3. Configure o token em `publisher.py`

### Bitly
1. Crie uma conta no Bitly
2. Gere um token de acesso
3. Configure o token em `publisher.py` e `metrics_analyzer.py`

### APIs de Afiliados
- **Amazon**: Requer Amazon Product Advertising API
- **Mercado Livre**: Requer API do Mercado Livre
- Atualmente usa dados simulados para demonstração

## Logs

- **Aplicação Flask**: Logs no console
- **Pipeline**: `curadoria_ofertas.log`
- **Cron**: `cron.log`

## Segurança

- Senhas hasheadas com bcrypt
- Autenticação via Flask-Login
- Validação de entrada em todas as APIs

## Limitações Atuais

1. **APIs Simuladas**: Coleta e métricas usam dados mock
2. **Tokens Não Configurados**: Requer configuração manual dos tokens
3. **Validação Básica**: Histórico de preços limitado aos dados coletados

## Próximos Passos

1. Integração com APIs reais da Amazon e Mercado Livre
2. Implementação de web scraping para Zoom e CamelCamelCamel
3. Integração com WhatsApp Business API
4. Dashboard de métricas mais avançado
5. Sistema de notificações por email

## Suporte

Para dúvidas ou problemas:
1. Verifique os logs de erro
2. Confirme se todas as dependências estão instaladas
3. Verifique se os tokens estão configurados corretamente
4. Teste a conectividade com as APIs externas

