"""Run from the project root: python -m scripts.check_publisher_access."""
import asyncio
import tempfile
from pathlib import Path

from app import article_context, core
from app.regional_sources_v10 import feeds_for_region


async def main():
    with tempfile.TemporaryDirectory() as directory:
        core.DATA_DIR = Path(directory)
        core.DB_PATH = core.DATA_DIR / "probe.db"
        core.init_db()
        article_context.init_db()
        for spec in feeds_for_region("All India"):
            try:
                data = await core._fetch_fixed_rss(spec.url)
                items = core.parse_rss(data, "All India", spec.name)
                if not items:
                    print(spec.name, "empty feed")
                    continue
                first = items[0]
                direct = await article_context._retrieve(first)
                print(spec.name, "direct", first["url"], article_context.public_status(direct), flush=True)
                query = first["title"][:125]
                matches = core.parse_rss(await core.fetch_rss(query), "All India")
                exact = next((a for a in matches if a["publisher"].casefold() == spec.name.casefold()
                              and core.title_tokens(a["title"]) == core.title_tokens(first["title"])), None)
                if exact:
                    core.unseen_articles(items)
                    result = await article_context._retrieve(exact)
                    print(spec.name, "Google RSS", article_context.public_status(result), flush=True)
                else:
                    print(spec.name, "Google RSS returned no exact publisher/headline pair", flush=True)
            except Exception as error:
                print(spec.name, type(error).__name__, str(error)[:150], flush=True)


if __name__ == "__main__":
    asyncio.run(main())
