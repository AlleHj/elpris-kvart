# Elpris Kvart (Home Assistant Integration). Version 1.0.5.

![Version](https://img.shields.io/badge/version-1.0.5-blue.svg)
![Home Assistant](https://img.shields.io/badge/home%20assistant-component-orange.svg)

**Elpris Kvart** är en anpassad integration (Custom Component) för Home Assistant som hämtar svenska elpriser (spotpriser) och presenterar dem med 15-minuters upplösning (kvartspriser). Integrationen hanterar automatiskt valutakonvertering, användarkonfigurerade påslag och ger dig totalpriset direkt i sensorer.

Denna integration är en vidareutveckling anpassad för den moderna elmarknaden där prissättning sker per kvart snarare än per timme.

## 🌟 Funktioner

* **Kvartspriser (15 min):** Hämtar och uppdaterar priser var 15:e minut (00, 15, 30, 45) för att matcha Nord Pools nuvarande standard.
* **Data från säker källa:** Hämtar data från [Elpriset just nu](https://www.elprisetjustnu.se) API.
* **Konfigurerbart påslag:** Lägg till ditt eget påslag (nätavgifter, energiskatt, moms, elhandlarens avgift) direkt via gränssnittet.
* **Dubbla valutor:** Visar priser i både **öre/kWh** (lättläst vid låga priser) och **SEK/kWh**.
* **Smarta Sensorer:** Separata sensorer för:
    * Ren spotpris.
    * Totalpris (Spot + Påslag).
    * Bara påslaget (för referens).
* **Framtidssäkrad:** Hämtar automatiskt morgondagens priser så fort de blir tillgängliga (efter kl 14:00).
* **Inga beroenden:** Kräver inga externa Python-bibliotek utöver Home Assistant standard.

---

## ⚙️ Installation

### Alternativ 1: HACS (Rekommenderas)
1.  Gå till HACS i Home Assistant.
2.  Klicka på "Integrations".
3.  Välj "Custom repositories" i menyn uppe till höger.
4.  Lägg till URL:en till detta repository: `https://github.com/AlleHj/elpris-kvart`
5.  Välj kategori **Integration**.
6.  Klicka på **Ladda ner**.
7.  Starta om Home Assistant.

### Alternativ 2: Manuell Installation
1.  Ladda ner källkoden från detta repository.
2.  Kopiera mappen `elpris_kvart` till din Home Assistant `config/custom_components/`-katalog.
3.  Starta om Home Assistant.

---

## 🚀 Konfiguration

När integrationen är installerad konfigurerar du den via Home Assistants gränssnitt:

1.  Gå till **Inställningar** -> **Enheter & Tjänster**.
2.  Klicka på **Lägg till integrering** längst ner till höger.
3.  Sök efter **Elpris Kvart**.
4.  Fyll i följande uppgifter:
    * **Elområde:** Välj ditt område (SE1, SE2, SE3 eller SE4).
    * **Elpåslag (öre/kWh):** Ange ditt totala påslag i öre (t.ex. `15.50` för 15,5 öre). Detta adderas till spotpriset i "Total"-sensorerna.

### Ändra påslag i efterhand
Du behöver inte installera om integrationen om ditt elavtal ändras.
1.  Gå till **Enheter & Tjänster** -> **Elpris Kvart**.
2.  Klicka på **Konfigurera**.
3.  Uppdatera ditt påslag i rutan som visas.
4.  Integrationen laddar om automatiskt med det nya värdet.

---

## 📊 Sensorer och Entiteter

Integrationen skapar en enhet med 6 sensorer för att ge dig full kontroll över datan.

| Sensor (Namn) | Beskrivning | Enhet | Uppdateras |
| :--- | :--- | :--- | :--- |
| **Spotpris i öre/kWh** | Det rena spotpriset från börsen. | öre/kWh | Varje kvart |
| **Spotpris + påslag i öre/kWh** | Spotpris plus ditt konfigurerade påslag. | öre/kWh | Varje kvart |
| **Spotpris i SEK/kWh** | Det rena spotpriset i kronor. | SEK/kWh | Varje kvart |
| **Spotpris + påslag i SEK/kWh** | Spotpris plus påslag i kronor. | SEK/kWh | Varje kvart |
| **Spotpris påslag Öre/kWh** | Visar ditt nuvarande inställda påslag. | öre/kWh | Vid ändring |
| **Spotpris påslag SEK/kWh** | Visar ditt påslag omräknat till kronor. | SEK/kWh | Vid ändring |

### Attribut
Sensorerna innehåller rik data (attribut) som kan användas för grafer eller automationer:
* `raw_today`: En lista med alla priser för innevarande dygn.
* `tomorrow_hourly_prices`: Priser för morgondagen (när tillgängligt).
* `min_price_today` / `max_price_today`: Dagens lägsta och högsta pris.
* `price_area`: Vilket elområde sensorn visar.

---

## 🛠 Teknisk Beskrivning

Denna integration är byggd för att vara resurssnål och tillförlitlig.

### Datahämtning och API
Integrationen använder en central `ElprisDataUpdateCoordinator` som kommunicerar med API:et `https://www.elprisetjustnu.se`.
* **Normal drift:** Data hämtas en gång per dygn för att minimera trafik.
* **Morgondagens priser:** Varje dag efter kl 14:00 (när börsen satt priserna) försöker integrationen hämta nästa dygns data. Om det misslyckas (t.ex. om API:et är sent), försöker den igen var 30:e minut.

### Kvarts-uppdateringar
Till skillnad från många äldre integrationer som bara uppdaterar varje timme, använder `Elpris Kvart` en smart timer-logik.
* Sensorerna räknar ut exakt när nästa kvart börjar (xx:00, xx:15, xx:30, xx:45).
* Vid exakt klockslag uppdateras sensorns värde från den lagrade prislistan. Detta säkerställer att du alltid ser det pris som gäller **just nu** utan fördröjning.

### Felhantering
Om API:et skulle ligga nere eller om internetförbindelsen bryts:
* Integrationen loggar varningar men kraschar inte.
* Om data saknas för en specifik tidpunkt visas sensorn som `unavailable` eller `unknown` tills data kan hämtas.

---

## ❓ Felsökning

**Jag ser inga sensorer efter installation?**
Kontrollera loggarna i Home Assistant. Se till att du startat om efter installationen.

**Priserna stämmer inte med mitt elbolag?**
Denna integration visar *Spotpriset*. Ditt elbolag kan ha andra påslag, certifikatsavgifter eller momsregler. Justera "Påslag"-inställningen i integrationen för att matcha din faktura så nära som möjligt.

**Hur aktiverar jag debug-loggning?**
Lägg till följande i din `configuration.yaml` eller aktivera det via integrationens sida i UI:
```yaml
logger:
  default: info
  logs:
    custom_components.elpris_kvart: debug
