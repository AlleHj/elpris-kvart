# home-assistant-elpris-timme

En anpassad Home Assistant-integration för att hämta och visa timpriser för el från elprisetjustnu.se.

## Funktionalitet

* Hämtar aktuella och (när tillgängligt) morgondagens spotpriser per timme för svenska elområden (SE1-SE4).
* Visar priser i både öre/kWh och SEK/kWh.
* Möjlighet att konfigurera ett fast påslag (i öre/kWh) som adderas till spotpriset.
* Sensorer för både spotpris och spotpris inklusive påslag.
* Sensorer som visar det konfigurerade påslaget.
* Dynamisk uppdateringsintervall för att hämta morgondagens priser effektivt.
* Konfigurerbar via Home Assistant UI (Config Flow och Options Flow).
* Möjlighet att aktivera detaljerad debug-loggning via UI.

## Chängelogg

### Version 0.1.3 (2025-05-28)

* **Ny Funktionalitet:**
    * **Hjälplänk i Konfiguration:**
        * En "?"-ikon visas nu i konfigurationsflödet (både initial setup och alternativ).
        * Länkar till en ny `HELP.md`-fil i repositoryt som beskriver de olika alternativen.
        * `manifest.json` uppdaterad med korrekt `documentation`-URL.
        * `config_flow.py` modifierad för att hämta och använda dokumentationslänken via `description_placeholders` och `strings.json`.
    * **Debug-läge via UI:**
        * En kryssruta "Aktivera debug-loggning" har lagts till i "Alternativ" för integrationen.
        * När den är aktiverad sätts komponentens loggnivå till `DEBUG`.
        * När den är inaktiverad sätts loggnivån till `INFO`.
        * Ändringen av loggnivån sker omedelbart när alternativet sparas, tack vare en uppdaterad `options_update_listener` i `__init__.py`.
        * Initial loggnivå sätts också vid uppstart av integrationen baserat på sparat alternativ.
        * Nya konstanter `CONF_DEBUG_MODE` och `DEFAULT_DEBUG_MODE` tillagda i `const.py`.
* **Förbättringar & Rättelser:**
    * `manifest.json`:
        * Korrekt `codeowners` och `issue_tracker`-URL (`AlleHj`).
        * `options_flow` satt till `true`.
        * Version uppdaterad till `0.1.3`.
    * `config_flow.py`:
        * Använder nu `strings.json` för felmeddelanden och beskrivningar mer konsekvent.
        * Säkerställer att `CONF_DEBUG_MODE` initialiseras i `options` när en ny config entry skapas.
    * `__init__.py`:
        * Förbättrad hantering av options-uppdateringar för att omedelbart justera loggnivån.
        * Mer detaljerad debug-loggning tillagd på flera ställen.
* **Nya Filer:**
    * `HELP.md`: Innehåller detaljerad hjälptext.
    * `strings.json`: Centraliserar UI-texter för konfiguration och alternativ.
    * `translations/sv.json`: Svensk översättning.
* **Filversioner uppdaterade till `2025-05-28-v0.1.3` för:**
    * `const.py`
    * `config_flow.py`
    * `__init__.py`

*(Tidigare versionhistorik kan läggas till här om så önskas)*