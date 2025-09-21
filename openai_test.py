# Minimal OpenAI test script for debugging 'proxies' error
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

try:
    response = openai.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": "Say hello world as JSON."}],
        temperature=0.0,
        max_completion_tokens=10,
    )
    print("LLM response:", response.choices[0].message.content)
except Exception as e:
    print("OpenAI error:", e)
