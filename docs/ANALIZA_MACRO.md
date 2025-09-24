## Analiză macro a proiectului

### Scop
Bot de trading pe Bybit (USDT perpetual) bazat pe semnale de lichidare detectate de pe Binance Futures.

### Arhitectură
- Semnale: Binance WS agregat (lichidări), `ccxt` pentru prețuri spot/futures (ticker/VWAP pe Binance).
- Execuție: Bybit API V5 (pybit) prin wrapper compatibil (`bybitwrapper.py`).
- Servicii:
  - `BybitUSDT/liquidation_ws.py`: detectează lichidări, aplică filtre (VWAP, `lick_value`), calculează qty și plasează ordinul Market pe Bybit.
  - `BybitUSDT/profit.py`: gestionează Take Profit/Stop pentru pozițiile existente.

### Flux de date
1. Binance WS → evenimente lichidare (`!forceOrder`), identifică simbolul (ex. `XRPUSDT` → `XRP`).
2. Ticker/VWAP (ccxt) → calculează condițiile de intrare.
3. Bybit (pybit) → plasează ordine, citește poziții, setează TP/SL.

### Puncte critice și remedieri
- API Bybit v2 (Swagger) depreciat → migrat la V5 (pybit) cu wrapper compatibil.
- Ordin respins sub 5 USDT → guard de notional + minime în `ordersize.json`.
- Crash la TP (IndexError) → selecție `entry_price` după `side`, fallback sigur.
- Stabilitate proces → supervisor PowerShell cu backoff + loguri.

### Configurabilitate
- `settings.json`: chei, `check_leverage`, `cooldown`.
- `coins.json`: simboluri, leverage, TP/SL, offsets VWAP, DCA, `lick_value`.
- `ordersize.json`: min_qty/stepSize/tickSize per simbol (recomandat să fie setate pentru perechile ieftine).

### Observații operaționale
- Implicit mainnet. Pentru testnet → `bybit(test=True)` + chei testnet.
- Respectă rate-limit-ul Bybit; în caz de erori, backoff scurt (1–3s) recomandat.
- Jurnalizare: `[ORDER_CHECK]`, `[ORDER_OK]`, `[ORDER_FAIL]` în WS; TP/SL anunțate în `profit.py`.

### Direcții viitoare
- Gating dinamic al simbolurilor (sidecar „active_symbols.json” pe baza volumului de lichidări).
- Normalizare strictă la `stepSize`/`tickSize` per simbol în calculele de qty/preț.
- Throttling per simbol (max N ordine în fereastră T) pentru controlul riscului.
- Export metrici/health (HTTP endpoint) pentru monitorizare externă.

