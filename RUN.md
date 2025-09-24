## Rulare Bybit-Futures-Bot (Windows, PowerShell)

### 0) Cerințe
- Windows 10/11
- Python instalat (Windows Launcher `py` sau `python`)

### 1) Creează și pornește mediul virtual (o singură dată)
```powershell
cd C:\Users\fred1\Desktop\Bybit-Futures-Bot
py -3 -m venv .venv
```

### 2) Instalează dependențele (o singură dată)
```powershell
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install pybit
```

### 3) Configurare
- Editați `settings.json` cu `key` și `secret` (atenție: mainnet!).
- Editați `coins.json` pentru simboluri și parametri.
- Setări minime pentru a trece regula Bybit ≥ 5 USDT în `ordersize.json`, ex.:
```json
{
  "BTC": 0.001,
  "ETH": 0.01,
  "XRP": 12,
  "DOGE": 30
}
```

### 4) Rulare simplă (două terminale)
- Terminal 1 – lichidări:
```powershell
cd C:\Users\fred1\Desktop\Bybit-Futures-Bot\BybitUSDT
..\.venv\Scripts\python liquidation_ws.py
```
- Terminal 2 – profit manager:
```powershell
cd C:\Users\fred1\Desktop\Bybit-Futures-Bot\BybitUSDT
..\.venv\Scripts\python profit.py
```

Oprire: `Ctrl + C` în fiecare terminal.

### 5) Rulare cu supraveghere (auto-restart și loguri)
Scriptul `run_bot_supervised.ps1` pornește ambele servicii, 
le repornește automat la cădere și scrie loguri în `logs/`.

```powershell
cd C:\Users\fred1\Desktop\Bybit-Futures-Bot
PowerShell -ExecutionPolicy Bypass -File .\run_bot_supervised.ps1
```

Loguri: `C:\Users\fred1\Desktop\Bybit-Futures-Bot\logs\*.log`

### 6) Note importante
- Botul este setat pe mainnet. Pentru testnet, în `BybitUSDT\bybitwrapper.py`, 
  schimbă `bybit(test=False, ...)` în `bybit(test=True, ...)` și folosește chei testnet.
- Botul ia prețuri și semnale din Binance (WS lichidări + ticker prin `ccxt`),
  dar plasează ordine pe Bybit (pybit V5).
- Dimensiunea ordinului ≈ (balanță USDT / preț) × leverage × `order_size_percent_balance`%, 
  respectând minimul din `ordersize.json` și pragul ≥ 5 USDT impus de Bybit.

### 7) Troubleshooting
- Eroare „Order does not meet minimum order value 5USDT”: crește minimul simbolului 
  în `ordersize.json` (min_qty ≈ ceil(5 / preț)).
- Eroare cont „UNIFIED/CONTRACT”: wrapper-ul folosește `UNIFIED` pentru citirea balanței.
- Dacă un serviciu se oprește, folosiți modul „supraveghere” sau reporniți manual.

 terminal 1

    cd C:\Users\fred1\Desktop\Bybit-Futures-Bot\BybitUSDT
    ..\.venv\Scripts\python liquidation_ws.py
 
 terminal 2 

     cd C:\Users\fred1\Desktop\Bybit-Futures-Bot\BybitUSDT
    ..\.venv\Scripts\python profit.py

Extra terminal (3)

  cd C:\Users\fred1\Desktop\Bybit-Futures-Bot
  PowerShell -ExecutionPolicy Bypass -File .\run_bot_supervised.ps1