import json
import asyncio
import logging
logging.basicConfig(level=logging.DEBUG)

from query.nl_to_cypher import get_nl_translator

async def main():
    t = get_nl_translator()
    result = await t.translate_query("which is the most powerful open source model today")
    print(json.dumps(result, indent=2, default=str))

asyncio.run(main())
