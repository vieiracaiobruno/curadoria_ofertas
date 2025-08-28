# Guia de Configuração de Tokens e APIs

Este documento detalha como configurar todos os tokens e APIs necessários para o funcionamento completo do sistema de curadoria de ofertas.

## 1. Bot do Telegram

### Criando o Bot
1. Abra o Telegram e procure por `@BotFather`
2. Envie `/newbot` para criar um novo bot
3. Escolha um nome para o bot (ex: "Ofertas Curadas Bot")
4. Escolha um username único (ex: "ofertas_curadas_bot")
5. O BotFather fornecerá um token no formato: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### Configurando o Token
Edite o arquivo `backend/modules/publisher.py`:
```python
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
```

### Obtendo IDs dos Canais
1. Adicione o bot aos seus canais do Telegram
2. Torne o bot administrador do canal
3. Para obter o ID do canal, envie uma mensagem no canal e use a API:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. O ID do canal aparecerá no formato `-100123456789`

## 2. Bitly (Encurtador de URLs)

### Criando Conta e Token
1. Acesse https://bitly.com e crie uma conta
2. Vá para Settings > Developer Settings
3. Clique em "Generate Access Token"
4. Copie o token gerado

### Configurando o Token
Edite os arquivos:

**backend/modules/publisher.py:**
```python
BITLY_ACCESS_TOKEN = "seu_token_bitly_aqui"
```

**backend/modules/metrics_analyzer.py:**
```python
BITLY_ACCESS_TOKEN = "seu_token_bitly_aqui"
```

## 3. Amazon Product Advertising API

### Requisitos
- Conta de vendedor na Amazon
- Aprovação para o programa de afiliados
- Aprovação para a Product Advertising API

### Configuração
1. Acesse https://webservices.amazon.com/paapi5/documentation/
2. Registre sua aplicação
3. Obtenha:
   - Access Key ID
   - Secret Access Key
   - Associate Tag (ID de afiliado)

### Implementação
Edite `backend/modules/collector.py` e substitua a função `_search_amazon_offers`:
```python
import boto3
from paapi5_python_sdk.api.default_api import DefaultApi
from paapi5_python_sdk.models.search_items_request import SearchItemsRequest

AMAZON_ACCESS_KEY = "sua_access_key"
AMAZON_SECRET_KEY = "sua_secret_key"
AMAZON_ASSOCIATE_TAG = "seu_associate_tag"
AMAZON_HOST = "webservices.amazon.com.br"  # Para Brasil
AMAZON_REGION = "us-east-1"
```

## 4. Mercado Livre API

### Configuração
1. Acesse https://developers.mercadolivre.com.br/
2. Registre sua aplicação
3. Obtenha:
   - Client ID
   - Client Secret

### Implementação
Edite `backend/modules/collector.py`:
```python
MERCADOLIVRE_CLIENT_ID = "seu_client_id"
MERCADOLIVRE_CLIENT_SECRET = "seu_client_secret"
```

## 5. APIs de Comparação de Preços

### Zoom (Buscapé)
Atualmente não possui API pública. Requer web scraping cuidadoso.

### CamelCamelCamel
Não possui API oficial. Alternativas:
- Keepa API (paga): https://keepa.com/#!api
- Web scraping (cuidado com rate limiting)

### Implementação Alternativa
Para começar, use o histórico próprio do sistema:
```python
# Em backend/modules/validator.py
# A validação já está implementada usando histórico próprio
# Adicione integração com APIs externas conforme necessário
```

## 6. WhatsApp Business API (Futuro)

### Requisitos
- Conta WhatsApp Business verificada
- Aprovação da Meta para API
- Webhook configurado

### Configuração (quando implementar)
1. Acesse https://developers.facebook.com/
2. Crie uma aplicação WhatsApp Business
3. Configure webhook e tokens

## 7. Configuração de Afiliados

### Amazon Associates
1. Cadastre-se em https://associados.amazon.com.br/
2. Obtenha seu Associate Tag
3. Configure URLs de afiliado no formato:
   ```
   https://www.amazon.com.br/dp/PRODUTO?tag=SEU_TAG&linkCode=ogi&th=1
   ```

### Mercado Livre Afiliados
1. Cadastre-se no programa de afiliados
2. Use o formato de URL:
   ```
   https://produto.mercadolivre.com.br/MLB-XXXXX?pdp_filters=category:MLB1234#searchVariation=XXXXX&position=1&search_layout=stack&type=item&tracking_id=SEU_ID
   ```

## 8. Configuração de Ambiente

### Variáveis de Ambiente (Recomendado)
Crie um arquivo `.env` na raiz do projeto:
```bash
# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Bitly
BITLY_ACCESS_TOKEN=seu_token_bitly

# Amazon
AMAZON_ACCESS_KEY=sua_access_key
AMAZON_SECRET_KEY=sua_secret_key
AMAZON_ASSOCIATE_TAG=seu_associate_tag

# Mercado Livre
MERCADOLIVRE_CLIENT_ID=seu_client_id
MERCADOLIVRE_CLIENT_SECRET=seu_client_secret

# Flask
FLASK_SECRET_KEY=sua_chave_secreta_super_forte
```

### Carregando Variáveis
Instale python-dotenv:
```bash
pip install python-dotenv
```

Modifique os arquivos para usar variáveis de ambiente:
```python
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
BITLY_ACCESS_TOKEN = os.getenv('BITLY_ACCESS_TOKEN')
```

## 9. Testes de Configuração

### Teste do Bot Telegram
```python
import requests

token = "SEU_TOKEN"
url = f"https://api.telegram.org/bot{token}/getMe"
response = requests.get(url)
print(response.json())
```

### Teste do Bitly
```python
import requests

token = "SEU_TOKEN"
headers = {"Authorization": f"Bearer {token}"}
url = "https://api-ssl.bitly.com/v4/user"
response = requests.get(url, headers=headers)
print(response.json())
```

## 10. Segurança

### Boas Práticas
1. **Nunca commite tokens no código**
2. **Use variáveis de ambiente**
3. **Rotacione tokens periodicamente**
4. **Configure rate limiting**
5. **Use HTTPS em produção**
6. **Monitore uso das APIs**

### Exemplo de .gitignore
```
.env
*.log
__pycache__/
*.pyc
backend/db/*.db
venv/
```

## 11. Monitoramento

### Logs de API
Configure logging para todas as chamadas de API:
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Em cada chamada de API
logger.info(f"Chamando API: {url}")
logger.info(f"Response: {response.status_code}")
```

### Alertas
Configure alertas para:
- Falhas de API
- Rate limiting
- Tokens expirados
- Erros de autenticação

## Suporte

Para problemas específicos de configuração:
1. Verifique a documentação oficial de cada API
2. Teste tokens individualmente
3. Monitore logs de erro
4. Verifique limites de rate das APIs

