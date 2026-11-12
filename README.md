# EAN Skener: telefon → PC → Abra

Telefon skenuje EAN kódy kamerou a PC je hned vepíše do políčka, ve kterém máš kurzor, třeba v Abře. Funguje to stejně jako USB čtečka.

- **Telefon:** webová aplikace (PWA) na `https://ean-skener.blue-kolman.workers.dev`, dá se přidat na plochu. Funguje na iPhonu i Androidu.
- **PC:** `EanAgent.exe` běží v oznamovací oblasti u hodin a přijaté kódy „píše na klávesnici“ a kopíruje do schránky.
- **Spojení** vede přes internet, přes bezplatný server na Cloudflare. Funguje v jakékoli Wi-Fi, i ve firemní nebo hostovské, a taky přes mobilní data. Telefon a PC nemusí být ve stejné síti.
- **Šifrování je end-to-end** (AES-256-GCM). Klíč je jen v párovacím QR kódu a server vidí pouze zašifrovaná data, nikoli samotné kódy.

## Instalace na PC

1. Stáhni `EanAgent-Setup-x.y.z.exe` z [GitHub Releases](https://github.com/bluebeing/ean-skener/releases/latest) a spusť ho. Práva správce nejsou potřeba.
   - Instalátor není digitálně podepsaný, takže Windows při prvním spuštění může ukázat modré okno „Systém Windows ochránil počítač“. Klikni na *Další informace → Přesto spustit*.
2. V průvodci můžeš zapnout *Spouštět automaticky po přihlášení* (výchozí) a zástupce na ploše.
3. Agent se nainstaluje do `%LOCALAPPDATA%\Programs\EAN Agent` a najdeš ho v nabídce Start jako **EAN Agent**.

**Aktualizace jsou automatické:** agent půl minuty po startu a pak každých 6 hodin zkontroluje nové vydání na GitHubu. Novou verzi stáhne, ověří kontrolní součet, potichu nainstaluje a znovu se spustí. Spárování telefonů zůstane. Ručně to jde přes *pravé tlačítko na ikoně → Zkontrolovat aktualizace*.

Odinstalace: *Nastavení → Aplikace → EAN Agent → Odinstalovat*.

## Spárování telefonu (jednou)

1. Spusť **EAN Agent**. Otevře se okno s QR kódem. Nahoře musí být „Připraveno, čekám na telefon“.
2. Naskenuj QR kód fotoaparátem telefonu. Otevře se skener a nahoře ukáže zeleně **„Připojeno k LAPTOP-…“**.
3. Přidej skener na plochu:
   - **Android:** *⋮ → Přidat na plochu / Instalovat aplikaci*. Spárování se přenese samo.
   - **iPhone:** *Sdílet → Přidat na plochu*. Aplikace na ploše má na iPhonu vlastní úložiště, takže ji po prvním otevření ještě jednou spáruj: klepni na **Naskenovat párovací QR** a namiř na QR kód na PC.

## Každodenní použití

1. Na PC klikni v Abře do políčka pro kód.
2. Na telefonu otevři **EAN Skener** → *Spustit skenování* → namiř na čárový kód.
3. Kód se vepíše a zároveň je ve schránce (Ctrl+V). Telefon pípne a problikne zeleně, pod kódem uvidíš název okna, kam se kód vepsal.

Stejný kód se znovu pošle až po 2 s bez záběru, takže se jeden produkt nenačte vícekrát omylem. Pro další kus stačí kód na chvíli oddálit a znovu namířit, nebo klepnout na kód v posledních kódech.

## Název produktu místo EANu (tabulka produktů)

Agent umí místo čísla EAN vepsat rovnou **název produktu** z tabulky. Tabulka zůstává jen na PC, telefon ani server ji nevidí.

1. V okně agenta klikni na **Vybrat tabulku…** (nebo v menu ikony *Vybrat tabulku produktů…*) a vyber soubor `.xlsx` nebo `.csv`.
2. Tabulka musí mít sloupec **EAN** a sloupec **Název**. Agent je pozná podle záhlaví, a když záhlaví chybí, podle obsahu. Ostatní sloupce se ignorují a použije se první list sešitu.
3. Nech zapnuté **Vepisovat název místo EANu**. V okně uvidíš, kolik produktů se načetlo.

Co se vepíše:

| Situace | Do Abry se vepíše | Telefon ukáže |
|---|---|---|
| EAN je v tabulce | název produktu | zeleně název |
| EAN v tabulce není | EAN | oranžově „EAN není v tabulce produktů“ |
| EAN má v tabulce víc různých názvů | EAN | oranžově „EAN má v tabulce víc názvů“ |
| Tabulka nejde načíst (smazaná, poškozená) | EAN | oranžově důvod |

- EANy s víc názvy ukáže tlačítko **Sporné EANy** v okně agenta. Oprav je v tabulce, aby měl každý EAN jen jeden název.
- Když tabulku upravíš a uložíš, agent ji do pár sekund načte znovu sám. Restart není potřeba.
- Do schránky jde to samé, co se vepsalo.

## QR kódy na produktech (EAN + šarže)

Skener čte kromě čárových kódů EAN i QR kódy produktů ve tvaru:

```
8595685258461L20261020E20270228
└─── EAN ───┘└ šarže ┘└expirace┘
```

- **EAN** (prvních 13 číslic) se zpracuje stejně jako čárový kód. Do Abry se vepíše název z tabulky, nebo EAN.
- **Šarže** (číslo za `L`, bez písmene L) jde **do schránky**, takže ji vložíš přes **Ctrl+V** jinde v Abře. Telefon ukáže „šarže … ve schránce“.
- **Expirace** (za `E`) se nepoužívá.

Šarže jde do schránky vždy, i když je vypnuté *Kopírovat kód do schránky*. Výjimkou je režim *Nepsat, jen zkopírovat do schránky*: v něm zůstane ve schránce název nebo EAN, protože se nikam nevepisuje.

Naskenováním párovacího QR kódu z okna agenta se telefon rovnou znovu spáruje.

## Nabídka v oznamovací oblasti (pravé tlačítko na ikoně)

| Položka | K čemu |
|---|---|
| Zobrazit párovací QR | znovu ukáže okno s QR kódem |
| Pozastavit příjem | telefon zobrazí „pozastaveno“ a nic se nevepíše |
| Po vepsání kódu | Nic (výchozí) / Enter / Tab |
| Způsob psaní | *Znaky* (výchozí). Když Abra běží přes **vzdálenou plochu** a kódy nedorazí, přepni na *Numerická klávesnice*. *Nepsat, jen zkopírovat do schránky* kód nikam nevepíše, vložíš ho sám přes Ctrl+V. |
| Kopírovat kód do schránky | zapnuto: každý kód (nebo název) jde navíc do schránky |
| Vepisovat název produktu místo EANu | zapnuto: s vybranou tabulkou se vepisuje název |
| Vybrat tabulku produktů… | výběr souboru `.xlsx` / `.csv` s EAN a názvy |
| Zrušit spárování všech telefonů | vygeneruje nový klíč, staré telefony se odpojí a je potřeba naskenovat nový QR |

## Když něco nefunguje

| Telefon ukazuje | Řešení |
|---|---|
| **PC je offline** | Agent na PC neběží, nebo PC nemá internet. Spusť `EanAgent.exe`. |
| **Neplatné spárování** | Na PC se spárování zrušilo. Klepni na *Naskenovat párovací QR* a naskenuj QR z okna agenta. |
| **Bez spojení se serverem** | Telefon nemá internet. |
| Vepsáno → ABRA…, ale v políčku nic | Abra běží jako správce. Spusť agenta taky jako správce (pravé tlačítko → Spustit jako správce). |

- **Nastavení a párovací klíč** jsou ve složce `data` v instalační složce agenta. Aktualizace ani odinstalace je nemažou. Klíč nikomu neposílej: kdo ho má, může do PC psát kódy.

## Vývoj

```
python -m venv .venv
.venv\Scripts\pip install -r agent\requirements.txt
.venv\Scripts\python agent\main.py          # spuštění agenta
.venv\Scripts\python tools\selftest.py      # test běžícího agenta přes relay (otevře testovací okno)
.venv\Scripts\python tools\test_products.py [tabulka.xlsx]   # offline test načítání tabulky produktů
build.bat                                   # sestaví dist\EanAgent\ a instalátor dist\EanAgent-Setup-<verze>.exe
```

`build.bat` potřebuje [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

**Vydání nové verze** (nainstalovaní agenti si ji stáhnou sami):

```
.\release.ps1 1.0.1 "Co je nového"
```

Skript nastaví verzi v `agent/version.py`, sestaví instalátor, **podepíše ho**, commitne, vytvoří tag `v1.0.1` a nahraje GitHub Release s instalátorem, kontrolním součtem `.sha256` a podpisem `.sig`.

**Podpisový klíč vydání** je v `%USERPROFILE%\.ean-skener\release-ed25519.pem`, mimo repozitář. Agent nainstaluje jen aktualizaci podepsanou tímto klíčem. **Klíč si zazálohuj** (např. do správce hesel) a nikam ho nenahrávej. Bez něj už nepůjde vydat aktualizaci, kterou si agenti nainstalují sami. Nové vydání by se pak muselo nainstalovat ručně, s novým veřejným klíčem v `agent/updater.py`.

## Zabezpečení

- **Šifrování end-to-end** (AES-256-GCM). Klíč je jen v párovacím QR kódu a nikdy neopustí telefon a PC. Server vidí jen zašifrovaná data, ID místnosti a počet připojených zařízení. Zprávy jsou svázané se směrem a místností, PC zahazuje zprávy starší než 60 s i zopakované zprávy.
- **PC vepíše jen** platný EAN (kontrolní číslice) nebo název z vlastní tabulky. Šarže smí obsahovat jen písmena a číslice. Žádné klávesové zkratky ani libovolný text.
- **Aktualizace** se instalují jen s platným podpisem Ed25519 a jen ze správné adresy na GitHubu, takže ani převzetí GitHub účtu nestačí k podvržení aktualizace.
- **Aplikace pro telefon** má přísnou Content Security Policy. Párovací QR se přijme jen pro vlastní server a přepárování na jiné PC je nutné potvrdit.
- **Párovací QR** se po prvním spárování už neukazuje při každém startu. Zobrazíš ho přes menu ikony. Kdo QR naskenuje, může do PC posílat kódy, takže ho neukazuj při sdílení obrazovky. Když unikne, použij *Zrušit spárování všech telefonů*.
- Bezpečnostní testy: `.venv\Scripts\python tools\test_security.py [http://127.0.0.1:8787]`

**Relay server (`relay/`)** je Cloudflare Worker s Durable Objects. Servíruje PWA z `pwa/` a přeposílá zprávy mezi telefonem a PC v „místnostech“.

```
cd relay
npm install
npx wrangler dev        # lokálně na http://localhost:8787 (agent: relay_url v dist\data\config.json)
npx wrangler deploy     # nasazení (po změně PWA nebo relay)
```

Struktura:
- `agent/`: Python agent (`relay_client.py` spojení, `crypto_box.py` šifrování, `typer.py` SendInput a schránka, `updater.py` aktualizace, `main.py` okno a tray)
- `installer/`: skript instalátoru Inno Setup
- `pwa/`: aplikace pro telefon (čisté HTML/JS). Kódy čte nativní `BarcodeDetector` (Android Chrome), jinak přibalený ZXing (`pwa/vendor/`, licence viz `LICENSE-*.txt`).
- `relay/`: Cloudflare Worker
