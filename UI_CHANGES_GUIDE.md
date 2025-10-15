# UI Changes Guide

This document describes the visual changes users will see in the application.

## Produtos Page Changes

### Visual Markers (Badges)

Products now display up to 3 badges at the top of each card to indicate status:

```
┌─────────────────────────────────────────────────────┐
│ [Na fila]      [Novo/Atualizado]         [Postado] │ ← Badges
│                                                     │
│  [Image]  Product Name                              │
│           Loja: Store Name                          │
│           Preço: R$ 99,99                           │
│           Tags: #tag1 #tag2                         │
│                                                     │
│  [Link] [Ativar loja] [Oferta] [Excluir]          │ ← Buttons
└─────────────────────────────────────────────────────┘
```

#### Badge Details:

1. **Top-Left - "Na fila" (Yellow/Warning)**
   - Shows when product has an offer waiting for approval
   - Color: Warning (yellow)
   - Icon: Clock
   - Helps identify products that need attention

2. **Top-Center - "Novo" or "Atualizado" (Blue/Gray)**
   - "Novo" (Blue): Product created in last 24 hours
   - "Atualizado" (Gray): Product updated in last 24 hours
   - Icon: Star (Novo) or Arrow-repeat (Atualizado)
   - Automatically disappears after 24 hours

3. **Top-Right - "Postado" (Green)**
   - Shows when product has been published to Telegram
   - Color: Success (green)
   - Icon: Check-circle
   - Helps avoid duplicate postings

### Button Changes

#### Before:
```
[Link] [Ativar loja] [Manter] [Excluir]
```

#### After:
```
[Link] [Ativar loja (disabled if active)] [Oferta] [Excluir]
```

**Key Changes:**
1. **"Ativar loja"** button now disabled when store is already active
   - Prevents unnecessary API calls
   - Visual feedback: grayed out, not clickable

2. **"Manter"** button replaced with **"Oferta"** button
   - New function: Sends product to approval queue
   - Color: Info (cyan/blue)
   - Icon: Send
   - Confirms action with user before sending

### Product Card Layout

The card maintains its position relative structure to show badges:
```css
position: relative;  /* on card */
position: absolute;  /* on badges */
z-index: 10;        /* ensures badges are on top */
```

## Ofertas Publicadas Page Changes

### Data Source Change

**Before:** Displayed current product data (which could have changed)

**After:** Displays snapshot of data from when offer was published

### Visual Impact

- Prices shown are **historical** (what was actually posted)
- Store names are **historical** (what was actually posted)
- Product names are **historical** (what was actually posted)
- This ensures accurate reporting and analytics

### Layout Remains Same

The table layout stays the same:
```
| Image | Product | Store | Offer Price | Original Price | Discount | Tags | Channels | Date | Link |
```

But the data comes from `ofertas_publicadas` table instead of `produtos` table.

## Lojas Confiaveis Page Changes

### Sorting

**Before:** Stores displayed in insertion order (random)

**After:** Stores sorted alphabetically by name (A-Z)

### Visual Impact

- Easier to find specific stores
- More professional appearance
- Better user experience when managing many stores

## Fila Aprovação Page Changes

### Telegram Messages

**Before:** Text-only messages sent to Telegram

**After:** Photo messages with caption sent to Telegram (when image available)

### Visual Impact

- Recipients see product image directly in Telegram
- More engaging and professional messages
- Matches format from run_pipeline flow
- Falls back to text message if photo fails

## Color Scheme

All badges follow Bootstrap 5 color conventions:

- **Success (Green)**: `bg-success` - Positive actions (Posted)
- **Warning (Yellow)**: `bg-warning text-dark` - Needs attention (In queue)
- **Info (Blue)**: `bg-info` - Informational (New)
- **Secondary (Gray)**: `bg-secondary` - Neutral info (Updated)

## Responsive Design

All changes maintain responsive design:
- Badges stack on mobile (may overlap slightly, which is fine)
- Buttons wrap naturally on small screens
- Cards adapt to grid layout (1 or 5 per row)

## JavaScript Interactions

### "Oferta" Button
```javascript
Click → Confirm dialog → API call → Success/Error message → Page reload
```

### Badge Updates
Badges update automatically when:
- Product is sent to queue (reload page)
- Product is approved (badge shown on next page load)
- 24 hours pass (new/updated badges disappear on next page load)

## Accessibility

All badges have `title` attributes for tooltips:
- Hover over badge to see full description
- Screen readers can announce badge purpose

## Performance Notes

- Badge calculations happen server-side (no JavaScript delays)
- Minimal impact on page load time
- Markers use simple datetime comparisons
- No additional database queries for badge data (uses eager loading)

## Browser Compatibility

All changes use standard HTML/CSS/JavaScript:
- Works in all modern browsers
- Bootstrap 5 icons used (already in project)
- No new external dependencies

## Print Styles

Badges will print with the page, helping with:
- Physical documentation
- Archival purposes
- Status reports
