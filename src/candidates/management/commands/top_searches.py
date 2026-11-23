"""What candidates search for: the most searched words, cities and skills.

    python manage.py top_searches              # last 30 days, top 20 of each
    python manage.py top_searches --days 7 --limit 10

"Searches with no results" are the words people wanted but no open job matched:
the jobs the site is missing.
"""

from django.core.management.base import BaseCommand, CommandParser

from candidates.search_log import search_stats


class Command(BaseCommand):
    help = "Show the most searched job words, cities and skills."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        stats = search_stats(days=options["days"], limit=options["limit"])
        days = options["days"]
        unit = "day" if days == 1 else "days"
        self.stdout.write(f"{stats.searches} searches in the last {days} {unit}.")
        sections = (
            ("Most searched words", stats.top_queries, "query"),
            ("Searches with no results", stats.no_result_queries, "query"),
            ("Most searched cities", stats.top_locations, "location"),
            ("Most searched skills", stats.top_skills, "name"),
        )
        for title, rows, field in sections:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))
            if not rows:
                self.stdout.write("  (none)")
            for row in rows:
                self.stdout.write(f"  {row['searches']:6}  {row[field]}")
