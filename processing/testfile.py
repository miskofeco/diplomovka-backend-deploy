from transformers import AutoTokenizer, AutoModelForCausalLM

# Load the model and tokenizer from Hugging Face
tokenizer = AutoTokenizer.from_pretrained("utter-project/EuroLLM-9B-Instruct")
model = AutoModelForCausalLM.from_pretrained("utter-project/EuroLLM-9B-Instruct")

# Define the system and user messages
system_message = "Si nápomocný asistent, ktorý odpovedá stručne a presne po slovensky."
user_message = "Vymenuj mi 3 výhody Pythonu ako programovacieho jazyka."

# Format the prompt according to the instruction template
prompt = f"""[INST] <<SYS>>
{system_message}
<</SYS>>

{user_message}
[/INST]"""

# Tokenize the prompt
inputs = tokenizer(prompt, return_tensors="pt")

# Generate a response from the model
outputs = model.generate(
    **inputs,
    max_length=512,
    do_sample=True,
    temperature=0.7
)

# Decode the generated tokens into text
response_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
print(response_text)