import ollama

# Definícia systémovej a užívateľskej správy
system_message = "Si nápomocný asistent, ktorý odpovedá stručne a presne po slovensky."
user_message = "Vymenuj mi 3 vyhody pythonu ako programovacieho jazyka"

# Formátovanie promptu podľa požiadaviek Mistral modelu
prompt = f"""[INST] <<SYS>>
{system_message}
<</SYS>>

{user_message}
[/INST]"""

# Generovanie odpovede
response = ollama.generate(model='llama3', prompt=prompt)

# Výpis výsledku
print(response['response'])