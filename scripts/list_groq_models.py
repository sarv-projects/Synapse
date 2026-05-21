from groq import Groq
import os
from dotenv import load_dotenv
load_dotenv()

key = os.environ.get("GROQ_API_KEYS", "").split(",")[0].strip()
c = Groq(api_key=key)
models = c.models.list()
for m in sorted(models.data, key=lambda x: x.id):
    print(m.id)
