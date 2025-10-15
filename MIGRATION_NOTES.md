# Migration Notes for Database Schema Changes

## Overview
This document describes the database schema changes required for the new offer management system.

## Changes to `produtos` table

Added columns to track product creation and update times:
- `data_criacao` (DATETIME, nullable): Timestamp when the product was first created
- `data_atualizacao` (DATETIME, nullable): Timestamp when the product was last updated

### SQL Migration (if needed):
```sql
ALTER TABLE produtos ADD COLUMN data_criacao DATETIME;
ALTER TABLE produtos ADD COLUMN data_atualizacao DATETIME;
```

## Changes to `ofertas_publicadas` table

Added columns to store snapshot of product and store data at the time of publication:
- `nome_produto` (VARCHAR, nullable): Product name at publication time
- `preco_original` (FLOAT, nullable): Original price at publication time
- `preco_oferta` (FLOAT, nullable): Offer price at publication time
- `desconto_real` (FLOAT, nullable): Discount percentage at publication time
- `url_afiliado_curta` (VARCHAR, nullable): Short affiliate URL at publication time
- `imagem_url` (VARCHAR, nullable): Product image URL at publication time
- `nome_loja` (VARCHAR, nullable): Store name at publication time
- `canal_nome` (VARCHAR, nullable): Channel name for quick reference

### SQL Migration (if needed):
```sql
ALTER TABLE ofertas_publicadas ADD COLUMN nome_produto VARCHAR(255);
ALTER TABLE ofertas_publicadas ADD COLUMN preco_original FLOAT;
ALTER TABLE ofertas_publicadas ADD COLUMN preco_oferta FLOAT;
ALTER TABLE ofertas_publicadas ADD COLUMN desconto_real FLOAT;
ALTER TABLE ofertas_publicadas ADD COLUMN url_afiliado_curta VARCHAR(500);
ALTER TABLE ofertas_publicadas ADD COLUMN imagem_url VARCHAR(500);
ALTER TABLE ofertas_publicadas ADD COLUMN nome_loja VARCHAR(255);
ALTER TABLE ofertas_publicadas ADD COLUMN canal_nome VARCHAR(255);
```

## Why These Changes?

### Problem with old design:
The `ofertas_publicadas` table only stored references to `ofertas.id` and `canais_telegram.id`. When viewing published offers, it would fetch the current data from `produtos` and `lojas_confiaveis` tables. This caused issues because:
1. Product prices change over time
2. Store names can change
3. Historical data about what was actually published was lost

### Solution with new design:
By storing a snapshot of the product and store data at publication time, we preserve the exact information that was sent to Telegram channels. This allows:
1. Accurate historical reporting
2. Correct tracking of which offers performed well
3. No confusion when product prices or store info changes

## Backward Compatibility

The new columns are all nullable, so existing records will still work. However, they won't have snapshot data. Only new publications (after this update) will have the snapshot data populated.

## Testing Notes

After applying these migrations:
1. Existing published offers will continue to display (using fallback to current Produto data where snapshot is null)
2. New offers approved and published will have snapshot data
3. The ofertas_publicadas page will prefer snapshot data over current product data
