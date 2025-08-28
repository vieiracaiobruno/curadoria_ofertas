# Sistema de Curadoria de Ofertas

Um sistema automatizado para coleta, validação e publicação de ofertas em canais do Telegram.

## Funcionalidades

- **Coleta Automatizada**: Raspagem de ofertas de lojas confiáveis (Amazon, Mercado Livre)
- **Validação Inteligente**: Sistema de aprovação/rejeição baseado em critérios configuráveis
- **Publicação Automática**: Envio de ofertas aprovadas para canais do Telegram
- **Painel de Controle**: Interface web para gerenciamento de ofertas e configurações
- **Análise de Métricas**: Acompanhamento de cliques e vendas

## Estrutura do Projeto

```
curadoria_ofertas/
├── app.py                     # Aplicação principal Flask
├── requirements.txt           # Dependências Python
├── config.env                 # Configurações (criar baseado em config.env.example)
├── logs/                      # Arquivos de log
├── backend/
│   ├── db/
│   │   └── database.py        # Configuração do banco de dados
│   ├── models/
│   │   └── models.py          # Modelos SQLAlchemy
│   ├── modules/
│   │   ├── collector.py       # Coleta de ofertas
│   │   ├── validator.py       # Validação de ofertas
│   │   ├── publisher.py       # Publicação no Telegram
│   │   └── metrics_analyzer.py # Análise de métricas
│   ├── routes/
│   │   └── api.py            # Rotas da API
│   └── utils/
│       └── auth.py           # Autenticação
├── frontend/
│   ├── templates/            # Templates HTML
│   └── static/              # Arquivos estáticos
└── run_pipeline*.py         # Scripts de execução do pipeline
```

## Instalação

1. **Clone o repositório**
   ```bash
   git clone <repository-url>
   cd curadoria_ofertas
   ```

2. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure as variáveis de ambiente**
   ```bash
   cp config.env.example config.env
   # Edite config.env com suas configurações
   ```

4. **Configure o banco de dados**
   ```bash
   python -c "from backend.db.database import create_db_tables; create_db_tables()"
   ```

5. **Execute a aplicação**
   ```bash
   python app.py
   ```

6. **Acesse o painel**
   - URL: http://localhost:5000
   - Usuário padrão: admin
   - Senha: (definida em config.env)

## Configuração

### Variáveis de Ambiente (config.env)

```env
# Database Configuration
DATABASE_URL=sqlite:///./backend/db/curadoria_ofertas.db

# Flask Configuration
SECRET_KEY=your-secret-key-change-this-in-production
FLASK_ENV=development
FLASK_DEBUG=True

# Admin Configuration
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-this-password
ADMIN_EMAIL=admin@example.com

# Logging Configuration
LOG_FILE=./logs/pipeline.log
RESULTS_FILE=./logs/pipeline_results.json

# Telegram Configuration
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHANNEL_ID=your-channel-id
```

### Configuração do Telegram

1. Crie um bot no Telegram usando @BotFather
2. Obtenha o token do bot
3. Adicione o bot ao canal onde deseja publicar as ofertas
4. Configure as variáveis `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHANNEL_ID`

## Uso

### Execução Manual do Pipeline

```bash
# Pipeline completo
python run_pipeline.py

# Pipeline simplificado (para testes)
python run_pipeline_simple.py
```

### Execução Automatizada

Configure um cron job para execução automática:

```bash
# Edite o crontab
crontab -e

# Adicione a linha (executa a cada 2 horas)
0 */2 * * * cd /path/to/curadoria_ofertas && python run_pipeline.py
```

## API Endpoints

### Ofertas
- `GET /api/canais_destino?tags=tag1,tag2` - Busca canais por tags
- `POST /api/ofertas/{id}/aprovar` - Aprova uma oferta
- `POST /api/ofertas/{id}/rejeitar` - Rejeita uma oferta
- `POST /api/ofertas/{id}/agendar` - Agenda uma oferta

### Configurações
- `POST /api/lojas` - Adiciona loja confiável
- `PUT /api/lojas/{id}` - Atualiza loja
- `DELETE /api/lojas/{id}` - Remove loja
- `POST /api/tags` - Adiciona tag
- `DELETE /api/tags/{id}` - Remove tag
- `POST /api/canais` - Adiciona canal Telegram
- `PUT /api/canais/{id}` - Atualiza canal
- `DELETE /api/canais/{id}` - Remove canal

## Desenvolvimento

### Estrutura de Dados

O sistema utiliza as seguintes entidades principais:

- **Usuario**: Usuários do sistema
- **LojaConfiavel**: Lojas para coleta de ofertas
- **Produto**: Produtos encontrados
- **Oferta**: Ofertas coletadas
- **Tag**: Categorização de produtos
- **CanalTelegram**: Canais de publicação
- **MetricaOferta**: Métricas de performance

### Adicionando Novas Lojas

1. Implemente o método de raspagem em `collector.py`
2. Adicione a loja via painel web ou API
3. Configure as tags apropriadas

## Troubleshooting

### Problemas Comuns

1. **Erro de importação**: Verifique se está no diretório correto
2. **Erro de banco**: Execute `create_db_tables()` novamente
3. **Erro de Telegram**: Verifique token e permissões do bot
4. **Erro de permissão**: Verifique se o diretório logs/ existe

### Logs

Os logs são salvos em:
- `./logs/pipeline.log` - Logs do pipeline
- `./logs/pipeline_results.json` - Resultados das execuções

## Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature
3. Commit suas mudanças
4. Push para a branch
5. Abra um Pull Request

## Licença

Este projeto está sob a licença MIT.
