# Hjälp för Elpris Timme Integrationen

Här hittar du information om de olika konfigurationsalternativen och inställningarna för Elpris Timme-integrationen.

## Konfigurationsalternativ (vid installation)

* **Elområde (`price_area`):**
    * **Beskrivning:** Välj ditt svenska elområde.
    * **Användning:** Används för att hämta korrekta timpriser för ditt geografiska område från elprisetjustnu.se.
    * **Möjliga värden:** SE1, SE2, SE3, SE4.

* **Påslag i öre/kWh (`surcharge_ore`):**
    * **Beskrivning:** Ange ditt totala påslag på spotpriset i öre per kWh. Detta inkluderar exempelvis elhandelsavgift, elcertifikat, ursprungsmärkning och moms på dessa avgifter. Ditt eventuella rörliga nätpris per kWh kan också inkluderas här om du vill se en mer komplett totalkostnad.
    * **Användning:** Adderas till det råa spotpriset för att ge en mer komplett bild av din timkostnad.
    * **Exempel:** `12.50` för 12,5 öre.

## Alternativ (efter installation)

Du kan komma åt dessa via "Alternativ" på integrationskortet.

* **Påslag i öre/kWh (`surcharge_ore`):**
    * **Beskrivning:** Samma som ovan, men kan justeras efter installationen.
    * **Användning:** Om du ändrar elavtal eller om påslagen justeras kan du uppdatera detta värde här.

* **Aktivera debug-loggning (`debug_mode`):**
    * **Beskrivning:** En kryssruta för att slå på eller av utökad loggning för felsökning.
    * **Användning:** När denna är aktiverad kommer integrationen att skriva mer detaljerad information till Home Assistants loggar. Detta är användbart om du upplever problem och vill se exakt vad integrationen gör. Stäng av för normal drift för att undvika onödigt stora loggfiler.
    * **Effekt:** Ändringen slår igenom omedelbart.