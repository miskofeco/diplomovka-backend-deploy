class SlovakPrompts:
    # Approach 1: Basic
    BASIC_SYSTEM = "Si užitočný asistent, ktorý vie dobre sumarizovať texty."
    BASIC_USER = (
        "Zosumarizuj nasledujúci článok do jedného odstavca s presne štyrmi vetami.\n"
        "Každá veta musí obsahovať kľúčové mená, čísla alebo fakty, aby sa text dal ľahko porovnať s referenčným zhrnutím.\n"
        "Zachovaj neutrálny novinársky tón a nepridávaj nové informácie.\n\n"
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
    BASELINE_SYSTEM = "Si stručný sumarizátor. Pracuješ s minimálnymi pokynmi a nevymýšľaš fakty, ktoré nie sú v texte."
    BASELINE_USER_WITH_TOPIC = (
        "Zhrň nasledujúci dokument k téme: '{topic}'.\n\n"
        "Dokument:\n{document}\n\n"
        "Napíš krátke zhrnutie zamerané na danú tému. Nepridávaj externé informácie."
    )
    BASELINE_USER_NO_TOPIC = (
        "Zhrň nasledujúci dokument do krátkeho odseku.\n"
        "Nepridávaj externé informácie ani predpoklady.\n\n"
        "Dokument:\n{document}"
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
        "Zhrnul som tento dokument{topic_clause}:\n\n"
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
        "Zhrnul som nasledujúci dokument{topic_clause}:\n\n"
        "{document}\n\n"
        "Zhrnutie:\n{summary}\n\n"
        "Spätná väzba na zhrnutie:\n{feedback}\n\n"
        "Uprav zhrnutie tak, aby už neobsahovalo chyby uvedené v spätnej väzbe.\n"
        "Urob minimum zmien a nepridávaj úvodné ani záverečné vety."
    )

    SUMMARY_RERANK_SYSTEM = "Vyberáš najvernejšie zhrnutie podľa dokumentu."
    SUMMARY_RERANK_USER = (
        "Dokument:\n{document}\n\n"
        "Téma: {topic}\n\n"
        "Kandidátne zhrnutie 1:\n{summary1}\n\n"
        "Kandidátne zhrnutie 2:\n{summary2}\n\n"
        "Vyber zhrnutie, ktoré má najmenej faktických nezrovnalostí s dokumentom.\n"
        'Vráť platný JSON: {"reasoning": "...", "answer": 1 alebo 2}\n'
        "Bez ďalšieho textu."
    )
