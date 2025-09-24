## Implementări efectuate

1) Migrare Bybit API la V5 (pybit) prin wrapper compatibil
- Fișier: `BybitUSDT/bybitwrapper.py`
- Înlocuit clientul Swagger învechit cu `pybit` V5 (unified trading).
- Expune clase compatibile: `LinearPositions`, `Wallet`, `LinearOrder`, `LinearConditional`, `Symbol`.
- Ajustat `Wallet_getBalance` la `accountType=UNIFIED`.

2) Reziliență la ordin și notional minim (≥ 5 USDT)
- Fișier: `BybitUSDT/liquidation_ws.py`
- Adăugat guard de notional (mărește cantitatea la minimul acceptat) înainte de a plasa ordinul.
- Try/except la plasarea ordinului (nu mai cade bucla la erori Bybit).

3) Fix TP/SL – selecție entry_price după side
- Fișier: `BybitUSDT/profit.py`
- `tp_calc` extrage `entry_price` în funcție de `side`, cu fallback sigur (prima poziție cu entry>0 sau ticker curent).
- Elimină `IndexError` când există o singură poziție.

4) Supervisor PowerShell pentru auto-restart și loguri
- Fișier: `run_bot_supervised.ps1`
- Pornește `liquidation_ws.py` și `profit.py`, repornește automat dacă ies, scrie loguri în `logs/`.

5) Ghid de rulare
- Fișier: `RUN.md` (RO)
- Pași instalați/rulare simplă și cu supraveghere.

Note:
- Scripturile rulează pe mainnet implicit. Pentru testnet: setează `bybit(test=True, ...)` și chei testnet.
- Pentru simboluri ieftine, configurează `BybitUSDT/ordersize.json` ca să treci pragul de 5 USDT.

