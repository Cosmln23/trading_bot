# Bot Bybit Futures – Ghid pentru Începători

Acest ghid îți arată pas cu pas cum să descarci proiectul, să instalezi dependențele, să configurezi cheile, să pornești fiecare componentă și cum să controlezi totul din Telegram. La final ai și explicații simple despre ce face fiecare modul.

Dacă vrei varianta scurtă: urmează „Start rapid”, apoi „Ce știe să facă”.

---

## 1) Cerințe

- Cont Bybit cu API key/secret (cont unificat)
- Cont Telegram (pentru alerte și comenzi)
- Python 3.10+ și pip
- Git (opțional, dar recomandat)

Verifică versiunile:
- Linux/macOS: `python3 --version` și `pip3 --version`
- Windows: `py --version` și `py -m pip --version`

---

## 2) Descarcă proiectul

Varianta A – Git clone (recomandat):

```
git clone https://github.com/your-user/Bybit-Futures-Bot.git
cd Bybit-Futures-Bot
```

Varianta B – Arhivă ZIP:
- Pe GitHub: „Code” → „Download ZIP”
- Dezarhivezi, apoi deschizi un terminal în folderul rezultat

---

## 3) Mediu virtual și instalare

Recomandat să folosești un mediu virtual (venv) separat.

Linux/macOS:
```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt -r requirements_panic.txt
```

Windows (PowerShell):
```
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3 -m pip install -U pip
pip install -r requirements.txt -r requirements_panic.txt
```

Dacă vezi „No module named pybit”, asigură-te că ai activat venv‑ul și reinstalează dependențele.

---

## 4) Configurare chei și setări

Editează aceste fișiere în rădăcina proiectului înainte de a porni ceva:

1) `settings.json`
- Completează `key` și `secret` cu API‑urile tale Bybit
- Setările de risc sunt gata pentru proiectul curent

Exemplu (câmpurile importante):
```
{
  "exchange": "bybit",
  "key": "<API_KEY>",
  "secret": "<API_SECRET>",
  "check_leverage": "false",
  "cooldown": 0.25,
  "risk_management": {
    "daily_max_dd_pct": 5,
    "daily_target_pct": 10,
    "equity_usdt": 350,
    "min_profit_usdt": 0.05,
    "breakeven_at_r": 0.5
  },
  "portfolio": {
    "enable": true,
    "market": "linear_1x",
    "buy_amount_usdt": 12,
    "max_open_positions": 4,
    "max_budget_pct": 40,
    "reserve_for_winloss_pct": 50,
    "scan_interval_sec": 300,
    "top_k": 5,
    "per_symbol_cooldown_min": 60,
    "entry": { "daily_change_min_pct": 5, "liq_notional_min_usd": 100, "allowlist_file": "allowlist_updated.json" },
    "score": { "w_daily_change": 0.6, "w_liq_usd": 0.4 },
    "risk": { "max_capital_pct": 60, "daily_target_pct": 3, "cooldown_minutes": 15 },
    "exit": { "initial_stop_pct": 3, "trail_from_peak_pct": 7, "hard_take_profit_pct": 20 },
    "pyramiding": { "enable": true, "add_on_move_pct": 4, "max_adds": 2 }
  }
}
```

2) `coins.json`
- Setări pe simbol pentru Win/Loss (TP/SL %, levier, mărime ordin %, offset‑uri VWAP, DCA). Proiectul are deja:
  - `take_profit_percent = 2.5`
  - `stop_loss_percent = 3`
  - `order_size_percent_balance = 11`
  - VWAP: majors `long=2 / short=5`, multe alts `1.5 / 4`

3) `config/panic.yaml` (Telegram și Panic Server)
- Pune acolo token‑ul de bot și chat id‑ul:
```
alert:
  telegram:
    bot_token: "<BOT_TOKEN_DE_LA_BOTFATHER>"
    chat_id: "<CHAT_ID>"
```
- Panic Server ascultă pe `127.0.0.1:8787` și acceptă doar local (implicit, sigur)

4) `allowlist_updated.json`
- Lista de simboluri permise pentru Portofoliu (ex. ["BTC","ETH","SOL",...])

Fișiere opționale:
- `ordersize.json` – min. order override pe simbol
- `risk_commands.json` – „comandă” pentru managerul de TP/SL (reduce/cancel la nevoie)

---

## 5) Pornește componentele

Deschide câte un terminal pentru fiecare (sau folosește `tmux`/`screen`). Activează venv‑ul în fiecare terminal.

1) Win/Loss – intrări pe lichidări (rapid):
```
python BybitUSDT/liquidation_ws.py
```

2) Profit Manager (TP/SL + control zilnic + IM%):
```
python BybitUSDT/profit.py
```
- Setează TP/SL folosind exact mărimea poziției (evită eroarea 110017)
- Oprește la profit zilnic +10% sau la pierdere zilnică −5% (închide tot și dezactivează tradingul)
- Monitorizează IM%: avertizează >80%, reduce automat 20% >100%
- Log în `pnl_log.csv` și stare zilnică în `state/daily_pnl.json`

3) Portofoliu Momentum (intrări lente, trend following):
```
python BybitUSDT/portfolio_manager.py
```
- Scanează la 300s, 1x levier, trailing stop, pyramiding, buget & top‑K
- Evită conflictele cu Win/Loss

4) Panic Button Server (închide tot imediat):
```
python panic_server.py
```
- Endpoint‑uri:
  - `POST /panic` – anulează ordine → închide poziții → verifică → blochează
  - `POST /panic/reset` – reset sigur dacă ești flat (fără poziții/ordine)
  - `GET /panic/status`, `GET /healthz`

5) Control prin Telegram (comenzi la distanță):
```
python telegram_bot_control.py
```
Comenzi în Telegram:
- `/status` – arată modulele active (Profit, Liquidation, Portfolio, Panic Server)
- `/kill` – oprește toate procesele botului
- `/close` (alias `/closeall`) – închide toate pozițiile și dezactivează tradingul
- `/help` – afișează comenzile

Windows:
- `run_bot_supervised.ps1` poate ajuta să rulezi totul într‑o singură fereastră

---

## 6) Start rapid (TL;DR)

1. Creează și activează venv
2. `pip install -r requirements.txt -r requirements_panic.txt`
3. Pune key/secret în `settings.json`
4. Pune token/chat_id în `config/panic.yaml`
5. Pornește în terminale separate:
   - `python panic_server.py`
   - `python BybitUSDT/profit.py`
   - `python BybitUSDT/liquidation_ws.py`
   - `python BybitUSDT/portfolio_manager.py` (opțional)
   - `python telegram_bot_control.py`
6. Folosește în Telegram: `/status`, `/close`

---

## 7) Ce știe să facă fiecare modul

- `BybitUSDT/liquidation_ws.py` – sistem Win/Loss:
  - Ascultă streamul de lichidări Binance Futures
  - Intrări pe baza VWAP cu offseturi per simbol
  - Respectă min. notional și pasul de cantitate per simbol
  - Sare peste simbolurile gestionate de Portofoliu (anti‑conflict)
  - Nu intră dacă IM% e mare (>80% avertisment, >100% blocare)

- `BybitUSDT/profit.py` – manager TP/SL & risc:
  - Setează TP/SL folosind mărimea poziției din exchange
  - Control zilnic: +10% profit sau −5% pierdere → închide tot și oprește
  - Monitorizare IM%: avertizează >80%, reduce 20% >100%
  - Evită spamul de ordine (idempotent)
  - Respectă panic lock și `trading_disabled.flag`
  - Log CSV în `pnl_log.csv`

- `BybitUSDT/portfolio_manager.py` – portofoliu momentum:
  - 1x levier, `buy_amount_usdt=12`, `max_open_positions=4`
  - Filtre intrare: variație zilnică %, lichiditate minimă, allowlist
  - Trailing din vârf, stop inițial, TP „hard” opțional
  - Pyramiding cu adăugări pe creștere
  - Stare: `portfolio_state.json`

- `panic_server.py` + directorul `panic/` – server HTTP de panică:
  - `/panic`: anulează ordine → închide poziții → verifică → pune lacăt
  - `/panic/reset`: deblochează doar dacă nu mai ai poziții/ordine
  - Acces restricționat la 127.0.0.1 (implicit)

- `telegram_bot_control.py` – control prin Telegram:
  - Comenzi: `/status`, `/kill`, `/close`, `/help`
  - Detectează procesele pornite și ca fișiere, și ca module

- Alte fișiere utile:
  - `settings.json` – setări globale (chei, risc, portofoliu)
  - `coins.json` – configurări Win/Loss pe simbol
  - `allowlist_updated.json` – lista de simboluri pentru portofoliu
  - `risk_commands.json` – comandă externă (închidere fracție / anulare)
  - `state/` – stare zilnică PnL, panic lock, etc.
  - `logs/` – jurnalizare

---

## 8) Depanare (probleme frecvente)

- `/close` spune „Could not initialize Bybit client”
  - Rulează `telegram_bot_control.py` în venv‑ul unde este instalat `pybit`
  - Reinstalează dependențele: `pip install -r requirements.txt -r requirements_panic.txt`

- Eroare Bybit 110017 (reduceOnly same side)
  - Botul folosește mărimea exactă a poziției și sensul corect; dacă apare, micșorează cantitatea la pasul de exchange sau lasă botul să refacă pe următoarea buclă

- `/status` nu arată Portofoliu sau Panic Server
  - Pornește Portofoliul cu `python BybitUSDT/portfolio_manager.py` sau `python -m BybitUSDT.portfolio_manager`
  - Pornește Panic Server cu `python panic_server.py` (sau `uvicorn panic.server:app`)

- Nu apar tranzacții sau „Unable to get price”
  - Verifică rețeaua și accesul la Binance/Bybit

- „Trading disabled by panic button”
  - Deblochează doar prin `POST /panic/reset` (sau șterge `state/panic.lock` și `trading_disabled.flag` doar dacă ești sigur că nu mai ai poziții/ordine)

---

## 9) Siguranță

- Ține cheile API private; nu le urca pe Git
- Panic Server rămâne pe 127.0.0.1; nu îl expune public
- Testează cu sume mici (sau pe testnet) înainte de producție

---

## 10) Actualizare bot

La actualizare din GitHub:
```
git pull
pip install -r requirements.txt -r requirements_panic.txt
```

Repornește componentele ca să ia noile schimbări.
