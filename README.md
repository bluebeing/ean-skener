# EAN Skener: telefon → PC → Abra

Telefon skenuje EAN kódy kamerou a PC je hned vepíše do políčka, ve kterém máš kurzor, třeba v Abře. Funguje to stejně jako USB čtečka.

- **Telefon:** webová aplikace (PWA) na `https://ean-skener.blue-kolman.workers.dev`, dá se přidat na plochu. Funguje na iPhonu i Androidu.
- **PC:** `EanAgent.exe` běží v oznamovací oblasti u hodin a přijaté kódy „píše na klávesnici“ a kopíruje do schránky.
- **Spojení** vede přes internet, přes bezplatný server na Cloudflare. Funguje v jakékoli Wi-Fi, i ve firemní nebo hostovské, a taky přes mobilní data. Telefon a PC nemusí být ve stejné síti.
- **Šifrování je end-to-end** (AES-256-GCM). Klíč je jen v párovacím QR kódu a server vidí pouze zašifrovaná data, nikoli samotné kódy.

## Spárování telefonu (jednou)

1. Spusť `dist\EanAgent.exe`. Otevře se okno s QR kódem. Nahoře musí být „Připraveno, čekám na telefon“.
2. Naskenuj QR kód fotoaparátem telefonu. Otevře se skener a nahoře ukáže zeleně **„Připojeno k LAPTOP-…“**.
3. Přidej skener na plochu:
   - **Android:** *⋮ → Přidat na plochu / Instalovat aplikaci*. Spárování se přenese samo.
   - **iPhone:** *Sdílet → Přidat na plochu*. Aplikace na ploše má na iPhonu vlastní úložiště, takže ji po prvním otevření ještě jednou spáruj: klepni na **Naskenovat párovací QR** a namiř na QR kód na PC.

## Každodenní použití

1. Na PC klikni v Abře do políčka pro kód.
2. Na telefonu otevři **EAN Skener** → *Spustit skenování* → namiř na čárový kód.
3. Kód se vepíše a zároveň je ve schránce (Ctrl+V). Telefon pípne a problikne zeleně, pod kódem uvidíš název okna, kam se kód vepsal.

Stejný kód se znovu pošle až po 2 s bez záběru, takže se jeden produkt nenačte vícekrát omylem. Pro další kus stačí kód na chvíli oddálit a znovu namířit, nebo klepnout na kód v posledních kódech.

## Nabídka v oznamovací oblasti (pravé tlačítko na ikoně)

| Položka | K čemu |
|---|---|
| Zobrazit párovací QR | znovu ukáže okno s QR kódem |
| Pozastavit příjem | telefon zobrazí „pozastaveno“ a nic se nevepíše |
| Po vepsání kódu | Nic (výchozí) / Enter / Tab |
| Způsob psaní | *Znaky* (výchozí). Když Abra běží přes **vzdálenou plochu** a kódy nedorazí, přepni na *Numerická klávesnice*. *Nepsat, jen zkopírovat do schránky* kód nikam nevepíše, vložíš ho sám přes Ctrl+V. |
| Kopírovat kód do schránky | zapnuto: každý kód jde navíc do schránky |
| Zrušit spárování všech telefonů | vygeneruje nový klíč, staré telefony se odpojí a je potřeba naskenovat nový QR |

## Když něco nefunguje

| Telefon ukazuje | Řešení |
|---|---|
| **PC je offline** | Agent na PC neběží, nebo PC nemá internet. Spusť `EanAgent.exe`. |
| **Neplatné spárování** | Na PC se spárování zrušilo. Klepni na *Naskenovat párovací QR* a naskenuj QR z okna agenta. |
| **Bez spojení se serverem** | Telefon nemá internet. |
| Vepsáno → ABRA…, ale v políčku nic | Abra běží jako správce. Spusť agenta taky jako správce (pravé tlačítko → Spustit jako správce). |

- **Automatický start s Windows:** `Win+R` → `shell:startup` → vlož tam zástupce na `EanAgent.exe`.
- **Nastavení a párovací klíč** jsou ve složce `data` vedle `EanAgent.exe`. **Při přesunu agenta přesuň i ji**, jinak bude potřeba telefony spárovat znovu. Klíč nikomu neposílej: kdo ho má, může do PC psát kódy.

## Vývoj

```
python -m venv .venv
.venv\Scripts\pip install -r agent\requirements.txt
.venv\Scripts\python agent\main.py          # spuštění agenta
.venv\Scripts\python tools\selftest.py      # test běžícího agenta přes relay (otevře testovací okno)
build.bat                                   # sestaví dist\EanAgent.exe
```

**Relay server (`relay/`)** je Cloudflare Worker s Durable Objects. Servíruje PWA z `pwa/` a přeposílá zprávy mezi telefonem a PC v „místnostech“.

```
cd relay
npm install
npx wrangler dev        # lokálně na http://localhost:8787 (agent: relay_url v dist\data\config.json)
npx wrangler deploy     # nasazení (po změně PWA nebo relay)
```

Struktura:
- `agent/`: Python agent (`relay_client.py` spojení, `crypto_box.py` šifrování, `typer.py` SendInput a schránka, `main.py` okno a tray)
- `pwa/`: aplikace pro telefon (čisté HTML/JS). Kódy čte nativní `BarcodeDetector` (Android Chrome), jinak přibalený ZXing (`pwa/vendor/`, licence viz `LICENSE-*.txt`).
- `relay/`: Cloudflare Worker
