class SlovakPrompts:
    # Approach 1: Basic
    BASIC_SYSTEM = "Si sumarizátor."
    BASIC_USER = (
        "Zosumarizuj nasledujúci článok.\n"
        "{article}"
    )

    # Approach 2: Enhanced Structured
    ENHANCED_SYSTEM = (
        "Si seniorný editor spravodajstva. Tvoríš presné, prirodzené a prehľadné zhrnutia, "
        "ktoré pôsobia ako hotový novinársky text pripravený na publikovanie."
    )
    ENHANCED_USER = (
        "Preštuduj článok a vytvor jedno odstavcové zhrnutie pozostávajúce presne zo štyroch viet v slovenčine.\n"
        "Dodrž nasledujúce zásady:\n"
        "1. Zachovaj hlavnú tému, všetky kľúčové osoby, inštitúcie a číselné údaje bez meniaceho významu.\n"
        "2. Používaj rovnaké pomenovania ako pôvodný text, keď sú fakty správne, aby jazyk zostal konzistentný.\n"
        "3. Vety prepájaj logickými spojkami, ukáž príčiny a dôsledky a zachovaj neutrálny tón.\n"
        "4. Nepoužívaj zoznamy, titulky ani hodnotiace výroky a nepridávaj fakty, ktoré v článku nie sú.\n"
        "5. Výsledok musí pôsobiť ako profesionálny novinársky odsek pripravený na publikovanie bez dodatočných komentárov.\n\n"
        "ČLÁNOK:\n{article}"
    )

    # Approach 3 & 4: Step 1 - Event Extraction
    EVENT_EXTRACTION_SYSTEM = (
        "Si analytik spravodajstva. Zachytávaš fakty a udalosti tak, aby z nich bolo možné zostaviť profesionálne a úplné zhrnutie."
    )
    EVENT_EXTRACTION_USER = (
        "Prečítaj si článok a vypíš 1 až 3 najrelevantnejšie udalosti vo formáte bulletov.\n"
        "Každý bod použite ako krátku vetu so štruktúrou: Kto – čo sa stalo – kedy – kde. Zachovaj presné názvy osôb, inštitúcií a čísla.\n"
        "Zameraj sa len na fakty, ktoré sú kľúčové pre pochopenie témy a neskôr vytvorenie zhrnutia.\n"
        "TEXT:\n{article}"
    )

    # Approach 3: Step 2 - Synthesis
    SYNTHESIS_USER = (
        "Na základe extrahovaných udalostí a pôvodného textu napíš finálne zhrnutie v jednom odstavci so štyrmi vetami.\n"
        "Každá veta musí vychádzať z uvedených udalostí, zachovaj mená, čísla a geografické názvy zo zdroja a udrž neutrálny tón.\n"
        "Pokry najprv kontext, potom hlavný výsledok a dôvody a napokon následky či plánované kroky.\n\n"
        "UDALOSTI:\n{events}\n\n"
        "KONTEXT:\n{article}\n\n"
        "FINÁLNE ZHRNUTIE:"
    )

    # Approach 4: Self-Evaluation
    EVALUATOR_SYSTEM = (
        "Si redaktor kontroly kvality. Posudzuješ pokrytie faktov, presnosť, koherenciu a jazykovú čistotu tak, "
        "aby výsledné zhrnutie zodpovedalo profesionálnym štandardom spravodajstva."
    )
    EVALUATOR_USER = (
        "Posúď, ako presne navrhované zhrnutie vystihuje článok. Skóre zakladaj na týchto otázkach:\n"
        "- Pokrýva hlavné fakty, čísla a mená?\n"
        "- Zachováva logické väzby a dôsledky bez pridania nových tvrdení?\n"
        "- Pôsobí jazykovo konzistentne s pôvodným textom a udržuje neutrálny tón?\n\n"
        "Článok:\n{article}\n\n"
        "Zhrnutie na posúdenie:\n{summary}\n\n"
        "Vráť LEN platný JSON v tvare:\n"
        "{{\n"
        '  "score": <0-10>,\n'
        '  "passed": <true/false>,\n'
        '  "feedback": "konkrétne pokyny na úpravu v slovenčine"\n'
        "}}\n"
        "Nastav passed=true iba vtedy, ak skóre >= 8 a text spĺňa všetky vyššie uvedené kritériá."
    )

    # Approach 4: Refinement
    REFINE_USER = (
        "Uprav predchádzajúce zhrnutie podľa spätnej väzby tak, aby znelo ako profesionálny spravodajský text a malo presne štyri vety.\n\n"
        "Pôvodný článok:\n{article}\n\n"
        "Aktuálne zhrnutie:\n{summary}\n\n"
        "Spätná väzba:\n{feedback}\n\n"
        "Uprav text tak, aby presne reflektoval pripomienky, zachoval číselné údaje a mená v rovnakom znení a nepridal neoverené informácie.\n"
        "Vylepšené zhrnutie:"
    )


class MammRefinePrompts:

    BASELINE_EVENTS_SYSTEM = (
        "Si analytik, ktorý rýchlo vyberá kľúčové udalosti a témy z textu bez pridania nových informácií."
    )
    BASELINE_EVENTS_USER = (
        "Si analytický asistent pre extrakciu udalostí a tém z textu. "
        "Tvojou úlohou je identifikovať kľúčové udalosti a hlavné témy, ktoré sú najdôležitejšie "
        "pre následnú sumarizáciu článku.\n\n"

        "INŠTRUKCIE:\n"
        "1. Pracuj výhradne s informáciami z DOKUMENTU. Nepredpokladaj nič mimo textu.\n"
        "2. Najprv si vnútorne identifikuj hlavné bloky deja: dôležité udalosti, rozhodnutia, konflikty, "
        "zmeny v čase a výsledky (čo sa stalo, kto, kde, kedy, s akým dôsledkom).\n"
        "3. Spájaj podobné alebo opakujúce sa informácie do jednej ucelenej udalosti/témy. "
        "Nevypisuj ten istý motív viac krát inými slovami.\n"
        "4. Uprednostni udalosti a témy, ktoré:\n"
        "   - výrazne menia situáciu alebo stav,\n"
        "   - súvisia s hlavnými aktérmi,\n"
        "   - obsahujú dôležité čísla, dátumy alebo výsledky,\n"
        "   - sú kľúčové pre pochopenie celkového príbehu článku.\n"
        "5. Zachovaj všetky dôležité fakty: osoby, miesta, čísla a časové údaje. "
        "Nezjednodušuj ich tak, aby sa zmenil význam.\n"
        "6. Vynechaj drobné detaily, ilustračné príklady a vedľajšie odbočky, ktoré nie sú kľúčové "
        "pre hlavnú líniu udalostí alebo tém.\n\n"

        "FORMÁT VÝSTUPU:\n"
        "- Vypíš 3 až 7 bodov.\n"
        "- Každý bod musí mať tvar: „- Krátky názov udalosti – 1 krátka veta s vysvetlením“.\n"
        "- Píš v slovenskom jazyku.\n"
        "- Nepopisuj svoj postup, vypíš len samotné body.\n\n"

        "DOKUMENT:\n{document}"
    )
    BASELINE_FROM_EVENTS_SYSTEM = "Si analytický asistent pre sumarizáciu textov, ktorý píše presné a kompaktné zhrnutia na základe faktov."
    BASELINE_FROM_EVENTS_ASSISTANT = (
        "Nižšie sú dva príklady článkov a referenčných zhrnutí, z ktorých sa máš inšpirovať pri tvorbe sumarizácie. "
        "Zachovaj faktickú presnosť, neutrálny tón a kompaktnosť.\n\n"
        "Príklad 1 — článok:\n"
        "EVERETT, Washington (Reuters) – Republikán Donald Trump v utorok večer nazval demokratov „stranou otroctva“ a chválil "
        "to, čo nazval miliónmi Afroameričanov s kariérnym úspechom, v rámci snahy oživiť svoj dosah na menšinových voličov. "
        "Trump vynaložil veľmi kritizované úsilie osloviť čiernych a hispánskych voličov, skupiny, ktoré vo všeobecnosti podporujú demokratov "
        "a očakáva sa, že vo voľbách 8. novembra budú vo veľkej miere hlasovať za Hillary Clintonovú.\n\n"
        "Referenčné zhrnutie:\n"
        "Donald Trump sa pokúsil získať si menšinových voličov tým, že nazval Demokratov „stranou otroctva“ na mítingu v štáte Washington. "
        "Počas svojho prejavu republikánsky prezidentský kandidát tiež pochválil Afroameričanov s kariérou. Trump bol predtým obvinený z "
        "predstavovania pochmúrneho obrazu životov černošských a hispánskych Američanov vo svojich pokusoch osloviť tieto skupiny. "
        "Jeho vyhlásenia viedli k obvineniam z rasizmu.\n\n"
        "Príklad 2 — článok:\n"
        "(Reuters) – Po 21 týždňoch pri kormidle Bieleho domu a oboch komôr amerického Kongresu, prezident Donald Trump a jeho republikáni "
        "zatiaľ neprijali žiadne významné zákony a majú málo času na to, aby tak urobili pred dlhou letnou prestávkou Washingtonu. "
        "Snemovňa reprezentantov sa znovu zišla v utorok. Bude zasadať ďalších deväť pracovných dní, rovnako ako Senát, ktorý sa znovu zišiel v pondelok. "
        "Obe komory si dajú prestávku od 1. do 9. júla, potom sa vrátia a budú pracovať od 10. do 28. júla. Potom bude na Capitol Hille ticho "
        "počas každoročnej augustovej dovolenky.\n\n"
        "Referenčné zhrnutie:\n"
        "Prezident Donald Trump a jeho Republikánska strana zatiaľ neschválili žiadnu významnú legislatívu pred nadchádzajúcou letnou prestávkou "
        "vo Washingtone, po viac ako 20 týždňoch pri moci. Trump sa zaviazal radikálne zmeniť Obamacare a schváliť výdavky na infraštruktúru, "
        "zníženie daní a regulácie; avšak, Kongres zatiaľ nedostal žiadne legislatívne návrhy k zásadným otázkam. Keď schválili návrh zákona "
        "o zvrátení Obamacare, ten sa neskôr zastavil v Senáte, zatiaľ čo plány daňovej reformy a politiky v oblasti infraštruktúry rozdelili "
        "Republikánov. Politickí analytici varovali, že kľúčové termíny pre rozpočty, ako aj voľby v roku 2018, taktiež ovplyvnia zvyšok roka 2017."
    )

    BASELINE_FROM_EVENTS_USER = (
    "Tvojou úlohou je vytvoriť vysoko relevantné a fakticky presné zhrnutie článku, "
    "ktoré vychádza z UDALOSTÍ A TÉM a z pôvodného DOKUMENTU.\n\n"

    "INŠTRUKCIE PRE SUMARIZÁCIU:\n"
    "1. Pracuj výhradne s informáciami z časti DOKUMENT. "
    "   Nepredpokladaj ani nedodávaj nič, čo nie je v dokumente explicitne alebo jednoznačne uvedené.\n"
    "2. Najprv si vnútorne identifikuj:\n"
    "   - najdôležitejšie udalosti a témy,\n"
    "   - hlavné aktérov (osoby, inštitúcie),\n"
    "   - kľúčové dátumy, čísla a výsledky,\n"
    "   - vzťahy príčina–následok a vývoj v čase,\n"
    "   ktoré súvisia s UDALOSŤAMI A TÉMAMI.\n"
    "3. Ak niektorá udalosť/téma z časti UDALOSTI A TÉMY v dokumente vôbec nevystupuje "
    "   alebo pre ňu v texte nie je jednoznačná opora, v zhrnutí ju nespomínaj.\n"
    "4. Uprednostni obsah s najvyššou informačnou hodnotou:\n"
    "   - hlavné tvrdenia a závery,\n"
    "   - kľúčové fakty (mená, čísla, dátumy),\n"
    "   - kauzálne súvislosti (čo k čomu viedlo),\n"
    "   - dôležité zmeny v čase.\n"
    "   Vynechaj irelevantné detaily, príklady a ilustrácie, ktoré neprispievajú k pochopeniu jadra udalostí/tém.\n"
    "5. Zachovaj neutrálny, vecný a stručný štýl bez hodnotiacich alebo emocionálnych komentárov.\n"
    "6. Výstup musí byť:\n"
    "   - jeden súvislý odsek,\n"
    "   - v slovenskom jazyku,\n"
    "   - stručný (približne 3–5 viet),\n"
    "   - bez odrážok, nadpisov a bez popisu vlastného postupu alebo úvah.\n"
    "7. Neprepisuj dlhé pasáže doslovne. Parafrázuj, ale presne zachovaj význam, fakty, mená, čísla a časové údaje.\n"
    "8. Ak dokument obsahuje viacero častí s rôznou dôležitosťou, zamerať sa máš najmä na tie, "
    "   ktoré najlepšie odpovedajú na UDALOSTI A TÉMY.\n\n"

    "UDALOSTI A TÉMY:\n{events}\n\n"
    "DOKUMENT:\n{document}\n\n"
    "ZHRNUTIE:"
)

    DETECT_SYSTEM = "Si dôsledný kontrolór faktov, ktorý označí vety nepodložené dokumentom."
    DETECT_USER = (
        "Dokument:\n{document}\n\n"
        "Veta na kontrolu:\n{sentence}\n\n"
        "Urči, či je veta fakticky konzistentná s dokumentom vyššie.\n"
        "Veta je konzistentná, ak ju dokument priamo uvádza alebo jednoznačne implikuje.\n\n"
        "Odpovedz stručne do 50 slov a vráť platný JSON:\n"
        '{"reasoning": "...", "answer": "yes" alebo "no"}\n'
        "Nepridávaj žiadny text mimo JSON."
    )

    CRITIQUE_SYSTEM = "Identifikuješ faktické chyby a navrhuješ presné opravy."
    CRITIQUE_USER = (
        "Zhrnul som tento dokument:\n\n"
        "{document}\n\n"
        "Zhrnutie:\n{summary}\n\n"
        "Problémová veta:\n{sentence}\n\n"
        "Vysvetli, ktorá časť vety alebo zhrnutia je fakticky nesprávna vzhľadom na dokument.\n"
        'Uveď dôvody, vyznač chybný úsek ako "Chybný úsek: <text>" a zakonči návrhom úpravy zhrnutia.\n'
        "Buď presný, neprepisuj celé zhrnutie, navrhni len nevyhnutnú zmenu."
    )

    CRITIQUE_RERANK_SYSTEM = "Porovnávaš dve kritiky a vyberáš tú presnejšiu a použiteľnejšiu."
    CRITIQUE_RERANK_USER = (
        "Vyber najlepšiu kritiku na zlepšenie faktickej správnosti.\n\n"
        "Dokument:\n{document}\n\n"
        "Zhrnutie:\n{summary}\n\n"
        "Kritika 1:\n{critique1}\n\n"
        "Kritika 2:\n{critique2}\n\n"
        "Vyber kritiku, ktorá najlepšie identifikuje faktickú chybu a obsahuje presný návrh opravy.\n"
        'Vráť platný JSON: {"reasoning": "...", "answer": 1 alebo 2}\n'
        "Bez ďalšieho textu."
    )

    REFINE_SYSTEM = "Si opatrný editor. Robíš len minimálne úpravy na opravu faktických chýb."
    REFINE_USER = (
        "Zhrnul som nasledujúci dokument:\n\n"
        "{document}\n\n"
        "Zhrnutie:\n{summary}\n\n"
        "Spätná väzba na zhrnutie:\n{feedback}\n\n"
        "Uprav zhrnutie tak, aby už neobsahovalo chyby uvedené v spätnej väzbe.\n"
        "Urob minimum zmien a nepridávaj úvodné ani záverečné vety."
    )

    SUMMARY_RERANK_SYSTEM = "Vyberáš najvernejšie zhrnutie podľa dokumentu."
    SUMMARY_RERANK_USER = (
        "Dokument:\n{document}\n\n"
        "Kandidátne zhrnutie 1:\n{summary1}\n\n"
        "Kandidátne zhrnutie 2:\n{summary2}\n\n"
        "Vyber zhrnutie, ktoré má najmenej faktických nezrovnalostí s dokumentom.\n"
        'Vráť platný JSON: {"reasoning": "...", "answer": 1 alebo 2}\n'
        "Bez ďalšieho textu."
    )
