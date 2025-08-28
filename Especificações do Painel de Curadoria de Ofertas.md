# Especificações do Painel de Curadoria de Ofertas

## Visão Geral
Sistema web para curadoria e aprovação de ofertas automatizadas encontradas por scraping. Interface responsiva e moderna para gerenciamento eficiente do fluxo de ofertas.

## Tecnologias Recomendadas
- **Backend**: Flask (Python) ou FastAPI
- **Frontend**: HTML5, CSS3, JavaScript
- **Framework CSS**: Bootstrap 5 ou Tailwind CSS
- **Banco de Dados**: SQLite
- **Ícones**: Bootstrap Icons ou Font Awesome

## Estrutura de Navegação
- **Header fixo**: Fundo azul escuro (#2c3e50 ou similar)
- **Logo**: "Admin Ofertas" com ícone
- **Menu**: Fila | Ofertas | Configurações
- **Área de usuário**: Ícone de perfil e botão logout

---

## Tela 1: Login
**Arquivo**: `login.html`

### Layout
- Página centralizada com formulário de login
- Header com logo "Admin Ofertas"
- Formulário simples e limpo

### Componentes
- **Campo Email**: Input type="email", placeholder="user@example.com"
- **Campo Senha**: Input type="password" com máscara de pontos
- **Botão Login**: Azul, largura total
- **Validação**: Mensagens de erro em vermelho abaixo dos campos

### Funcionalidades
- Validação client-side básica
- Redirecionamento para dashboard após login
- Proteção contra acesso não autorizado

---

## Tela 2: Fila de Aprovação (Principal)
**Arquivo**: `fila_aprovacao.html`

### Layout
- Header com navegação
- Título "Fila de Aprovação (X)" com contador dinâmico
- Lista de cards de ofertas em layout responsivo

### Card de Oferta - Especificações Detalhadas

#### Estrutura do Card
```
[Imagem do Produto] | [Informações e Ações]
```

#### Seção de Informações
1. **Título do Produto**: H5, texto completo, quebra de linha automática
2. **Vendedor**: Texto pequeno, cinza, formato "Vendido por [Nome da Loja]"
3. **Preços**: 
   - Preço atual: Grande, verde, negrito (ex: R$ 4.599,00)
   - Preço anterior: Riscado, cinza (ex: ~~R$ 5.199,00~~)
4. **Validação**: Badge colorido com ícone e texto explicativo
   - 🔥 "Menor preço dos últimos 90 dias" (laranja/vermelho)
   - 📈 "X% abaixo da média" (verde)
   - ⏰ "Preço validado há X horas" (azul)

#### Seção de Categorização
1. **Tags Editáveis**:
   - Badges azuis clicáveis com "X" para remover
   - Input para adicionar novas tags
   - Sugestões automáticas baseadas no produto
2. **Canais de Destino**:
   - Lista dinâmica baseada nas tags selecionadas
   - Ícone do Telegram + nomes dos canais

#### Botões de Ação
- **Rejeitar**: Vermelho, ícone lixeira
- **Agendar**: Cinza, ícone relógio
- **Aprovar e Postar**: Verde, ícone check

### Funcionalidades JavaScript
- Remoção de tags em tempo real
- Adição de novas tags com Enter
- Atualização automática dos canais de destino
- Confirmação antes de rejeitar/aprovar
- Contador dinâmico no título

---

## Tela 3: Ofertas Publicadas
**Arquivo**: `ofertas_publicadas.html`

### Layout
- Header com navegação
- Título "Ofertas Publicadas"
- Seção de filtros
- Tabela de dados com paginação

### Seção de Filtros
1. **Período**: Date range picker (ex: 01/04/2024 - 24/04/2024)
2. **Categoria**: Dropdown com todas as tags disponíveis
3. **Busca**: Campo de texto para buscar por nome do produto

### Tabela de Métricas
#### Colunas:
1. **Imagem**: Thumbnail 50x50px
2. **Nome do Produto**: Texto truncado com tooltip completo
3. **Preço**: Valor da oferta quando publicada
4. **Data de Publicação**: Formato DD/MM/AAAA
5. **Cliques**: Número obtido via API Bitly
6. **Vendas**: Número de conversões
7. **Taxa de Conversão**: Percentual (Vendas/Cliques)

#### Funcionalidades:
- Ordenação por qualquer coluna (clique no header)
- Paginação (10, 25, 50 itens por página)
- Exportação para CSV/Excel
- Cores condicionais (verde para alta conversão, vermelho para baixa)

---

## Tela 4: Configurações
**Arquivo**: `configuracoes.html`

### Layout em 3 Seções

#### 1. Gerenciar Lojas Confiáveis
- **Tabela com colunas**:
  - Nome da Loja
  - Plataforma (Amazon/Mercado Livre)
  - Pontuação de Confiança (1-5 estrelas)
  - Status Ativo (toggle switch)
- **Botão**: "Adicionar Loja" (modal popup)

#### 2. Gerenciar Tags
- **Tags existentes**: Badges coloridos removíveis
- **Campo**: Input para criar nova tag
- **Funcionalidade**: Arrastar e soltar para reordenar

#### 3. Gerenciar Canais
- **Tabela com colunas**:
  - Nome do Canal
  - Tags Associadas (badges)
  - Número de Inscritos
  - Ações (Editar/Excluir)
- **Botão**: "Adicionar Canal" (modal popup)

---

## Especificações Técnicas de Responsividade

### Breakpoints
- **Mobile**: < 768px (cards empilhados, tabelas com scroll horizontal)
- **Tablet**: 768px - 1024px (layout adaptado)
- **Desktop**: > 1024px (layout completo)

### Adaptações Mobile
1. **Cards de Oferta**: Stack vertical, botões em largura total
2. **Tabelas**: Scroll horizontal ou cards colapsáveis
3. **Filtros**: Accordion colapsável
4. **Navegação**: Menu hamburger

---

## Estados e Interações

### Loading States
- Skeleton screens durante carregamento
- Spinners em botões durante ações
- Placeholders para imagens não carregadas

### Feedback Visual
- Toast notifications para ações (sucesso/erro)
- Confirmações para ações destrutivas
- Hover effects em elementos clicáveis
- Disabled states para botões processando

### Validações
- Campos obrigatórios marcados
- Mensagens de erro contextuais
- Validação em tempo real para formulários

---

## Paleta de Cores Sugerida
- **Primário**: #3498db (azul)
- **Sucesso**: #27ae60 (verde)
- **Perigo**: #e74c3c (vermelho)
- **Aviso**: #f39c12 (laranja)
- **Secundário**: #95a5a6 (cinza)
- **Fundo**: #f8f9fa (cinza claro)
- **Texto**: #2c3e50 (azul escuro)

---

## Considerações de Performance
- Lazy loading para imagens de produtos
- Paginação server-side para tabelas grandes
- Cache de dados de configuração
- Compressão de assets CSS/JS
- Otimização de imagens (WebP quando possível)

---

## Segurança
- Autenticação obrigatória em todas as páginas
- Validação server-side de todos os inputs
- Proteção CSRF em formulários
- Sanitização de dados de entrada
- Logs de auditoria para ações críticas

