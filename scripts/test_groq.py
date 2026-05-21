from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()

keys = os.environ.get("GROQ_API_KEYS", "").split(",")
print(f"Testing {len(keys)} key(s)...")

for i, key in enumerate(keys):
    key = key.strip()
    try:
        c = Groq(api_key=key)
        r = c.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "say hi in one word"}],
            max_tokens=5
        )
        print(f"Key {i}: OK — {r.choices[0].message.content}")
    except Exception as e:
        print(f"Key {i}: FAILED — {e}")
