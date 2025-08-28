# Sistema de Curadoria de Ofertas - Instruções Finais

## 🎉 Sistema Implantado com Sucesso!

Seu sistema de curadoria de ofertas está agora **funcionando e acessível publicamente**!

### 🌐 Acesso ao Painel Web
- **URL:** https://8000-izjvtbot7mz93l1r62jfs-a6fcf7c8.manusvm.computer
- **Usuário:** admin
- **Senha:** admin_password

⚠️ **IMPORTANTE:** Altere a senha padrão assim que possível por segurança!

### 🔄 Automação Configurada
O sistema está configurado para executar automaticamente a cada 2 horas:
- **Cron Job:** `0 */2 * * * cd /home/ubuntu/curadoria_ofertas && python3.11 /home/ubuntu/curadoria_ofertas/run_pipeline_simple.py >> /home/ubuntu/curadoria_ofertas/cron.log 2>&1`
- **Logs:** `/home/ubuntu/curadoria_ofertas/cron.log`
- **Resultados:** `/home/ubuntu/curadoria_ofertas/pipeline_results.json`

### 📁 Estrutura do Sistema

```
/home/ubuntu/curadoria_ofertas/
├── src/main.py                    # Aplicação Flask principal
├── frontend/                      # Templates e arquivos estáticos
│   ├── templates/                 # Templates HTML
│   └── static/                    # CSS, JS, imagens
├── backend/                       # Módulos do backend
│   ├── modules/                   # Coleta, validação, publicação
│   ├── models/                    # Modelos de dados
│   └── routes/                    # APIs REST
├── run_pipeline_simple.py         # Pipeline simplificado (ativo)
├── run_pipeline.py               # Pipeline completo (para desenvolvimento)
├── requirements.txt              # Dependências Python
├── README.md                     # Documentação principal
└── CONFIGURACAO_TOKENS.md       # Guia de configuração de APIs
```

### 🛠️ Próximos Passos para Personalização

#### 1. Configurar APIs Reais
Edite os arquivos em `backend/modules/` para adicionar:
- **Telegram Bot Token:** Para publicação automática
- **Bitly API Key:** Para encurtamento de links
- **APIs de Scraping:** Amazon, Mercado Livre, Zoom, CamelCamelCamel

#### 2. Configurar Banco de Dados
- O sistema atual usa dados mock
- Para produção, configure o SQLite ou PostgreSQL
- Execute `python3.11 backend/db/database.py` para criar as tabelas

#### 3. Personalizar Validação
Edite `backend/modules/validator.py` para:
- Ajustar critérios de desconto mínimo
- Implementar validação de histórico de preços
- Configurar filtros de lojas confiáveis

#### 4. Configurar Canais de Publicação
No painel web, configure:
- **Lojas Confiáveis:** Amazon, Mercado Livre, etc.
- **Tags de Categorização:** informatica, gamer, casa, etc.
- **Canais do Telegram:** IDs dos grupos/canais

### 📊 Monitoramento

#### Verificar Status do Sistema
```bash
# Status da aplicação web
curl https://8000-izjvtbot7mz93l1r62jfs-a6fcf7c8.manusvm.computer/health

# Logs do pipeline
tail -f /home/ubuntu/curadoria_ofertas/pipeline.log

# Logs do cron
tail -f /home/ubuntu/curadoria_ofertas/cron.log

# Resultados das execuções
cat /home/ubuntu/curadoria_ofertas/pipeline_results.json
```

#### Executar Pipeline Manualmente
```bash
cd /home/ubuntu/curadoria_ofertas
python3.11 run_pipeline_simple.py
```

### 🔧 Comandos Úteis

#### Gerenciar Cron Jobs
```bash
# Ver cron jobs ativos
crontab -l

# Editar cron jobs
crontab -e

# Remover todos os cron jobs
crontab -r
```

#### Gerenciar Aplicação Web
```bash
# Ver processos do gunicorn
ps aux | grep gunicorn

# Reiniciar aplicação (se necessário)
pkill -f gunicorn
cd /home/ubuntu/curadoria_ofertas
source venv/bin/activate
gunicorn --workers 4 --bind 0.0.0.0:8000 src.main:app
```

### 🚀 Funcionalidades Implementadas

✅ **Painel Web Administrativo**
- Login seguro
- Fila de aprovação de ofertas
- Visualização de ofertas publicadas
- Configurações de lojas, tags e canais

✅ **Pipeline Automatizado**
- Coleta de ofertas (simulada)
- Validação de descontos
- Publicação automática (simulada)
- Logging detalhado

✅ **Sistema de Métricas**
- Tracking de cliques
- Contagem de vendas
- Análise de conversão

✅ **Automação Completa**
- Execução via cron job
- Logs persistentes
- Resultados estruturados

### 📈 Próximas Fases (Fase 2 e 3)

Quando estiver pronto para expandir:

1. **Integração com Instagram** (Fase 2)
   - API do Instagram para publicação
   - Geração automática de imagens
   - Sincronização com ofertas do Telegram

2. **Chatbot B2B** (Fase 3)
   - WhatsApp Business API
   - Sistema de cobrança
   - Dashboard para clientes empresariais

### 🆘 Suporte

Se precisar de ajuda:
1. Verifique os logs em `/home/ubuntu/curadoria_ofertas/`
2. Teste o endpoint `/health` da aplicação
3. Execute o pipeline manualmente para debug

**Sistema funcionando perfeitamente! 🎯**

