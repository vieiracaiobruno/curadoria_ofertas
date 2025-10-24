# Coletor da Amazon - Guia de Uso

## Visão Geral

O `AmazonCollector` é um módulo de coleta de ofertas da Amazon Brasil que segue o mesmo padrão do `MLCollector`, permitindo integração perfeita com o pipeline de curadoria de ofertas existente.

## Arquitetura

### Passo 1: Exportação de Cookies
- Utiliza Selenium para acessar a Amazon Brasil
- Exporta cookies atualizados da sessão do navegador
- Permite autenticação para coleta de dados

### Passo 2: Coleta de Links de Produtos
- Acessa a página de ofertas do dia da Amazon via requisições HTTP
- Extrai todos os links de produtos disponíveis
- Suporta paginação (número de páginas configurável)

### Passo 3: Extração de Dados de Produtos
- Para cada link de produto coletado:
  - Faz requisição HTTP para a página do produto
  - Extrai informações detalhadas usando BeautifulSoup
  - Valida e formata os dados

### Passo 4: Envio para Processamento
- Retorna lista de dicts no formato esperado pelo `OfferProcessor`
- Compatível com o fluxo de validação e publicação existente

## Configuração

### Variáveis de Ambiente

Adicione as seguintes variáveis ao arquivo `config.env`:

```env
# Habilitar/desabilitar coletor da Amazon
ENABLE_AMAZON_COLLECTOR=false

# Configurações do coletor
AMAZON_MAX_PAGES=3              # Número de páginas de ofertas para coletar
AMAZON_REQUEST_DELAY_SEC=2      # Delay entre requisições (segundos)
```

## Uso

### Modo Standalone

Para testar apenas o coletor da Amazon:

```bash
python scripts/iniciar_scrapper_amazon.py
```

### Integrado ao Pipeline

1. Habilite o coletor no `config.env`:
   ```env
   ENABLE_AMAZON_COLLECTOR=true
   ```

2. Execute o pipeline completo:
   ```bash
   python run_pipeline.py
   ```

## Campos Extraídos

| Campo | Descrição |
|-------|-----------|
| `url_base` | URL do produto na Amazon |
| `id_product` | ASIN do produto |
| `seller_id` | ID do vendedor |
| `store_name` | Nome da loja/vendedor |
| `preco_original` | Preço original |
| `preco_oferta` | Preço com desconto |
| `desconto` | Percentual de desconto |
| `nome_produto` | Nome do produto |
| `imagem_url` | URL da imagem |
| `seller_score` | Pontuação do vendedor |
