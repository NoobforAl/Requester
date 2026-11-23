"""Write saved_objects.ndjson: the Kibana data views and the Requester dashboard.

    python elastic/kibana/build_saved_objects.py

Edit the panels here (not in the ndjson), run it, and commit both files.
``make analytics-up`` imports the ndjson (import.sh), overwriting what is there,
so changes made in the Kibana UI are lost: save a copy under another name first.
"""

import json
from pathlib import Path

OUT = Path(__file__).with_name("saved_objects.ndjson")
#: Width of a Kibana dashboard grid.
GRID_COLUMNS = 48

# ------------------------------------------------------------------ data views
#: id -> (index, name, time field or None). No time field: the dashboard's time
#: range does not apply (current state: postings, candidates).
DATA_VIEWS = {
    "requester-postings": ("requester-postings", "Job postings (now)", None),
    "requester-applications": (
        "requester-applications",
        "Applications (by date applied)",
        "applied_at",
    ),
    "requester-application-events": (
        "requester-application-events",
        "Application status changes",
        "created_at",
    ),
    "requester-searches": ("requester-searches", "Job searches", "created_at"),
    "requester-candidates": ("requester-candidates", "Candidates (now)", None),
    "requester-daily-stats": ("requester-daily-stats", "Daily totals", "day"),
}


def data_view(view_id: str) -> dict:
    index, name, time_field = DATA_VIEWS[view_id]
    attributes = {"title": index, "name": name}
    if time_field:
        attributes["timeFieldName"] = time_field
    return {
        "type": "index-pattern",
        "id": view_id,
        "attributes": attributes,
        "references": [],
        "typeMigrationVersion": "8.0.0",
    }


# --------------------------------------------------------------- lens columns
def count(label: str, kql: str = "") -> dict:
    column = {
        "label": label,
        "customLabel": True,
        "dataType": "number",
        "operationType": "count",
        "isBucketed": False,
        "scale": "ratio",
        "sourceField": "___records___",
        "params": {"emptyAsNull": False},
    }
    if kql:
        column["filter"] = {"query": kql, "language": "kuery"}
    return column


def metric(operation: str, field: str, label: str, **params) -> dict:
    return {
        "label": label,
        "customLabel": True,
        "dataType": "number",
        "operationType": operation,
        "isBucketed": False,
        "scale": "ratio",
        "sourceField": field,
        "params": {"emptyAsNull": True, **params},
    }


def terms(field: str, label: str, size: int, order_by: str = "m") -> dict:
    return {
        "label": label,
        "customLabel": True,
        "dataType": "string",
        "operationType": "terms",
        "isBucketed": True,
        "scale": "ordinal",
        "sourceField": field,
        "params": {
            "size": size,
            "orderBy": {"type": "column", "columnId": order_by},
            "orderDirection": "desc",
            "otherBucket": False,
            "missingBucket": False,
            "parentFormat": {"id": "terms"},
        },
    }


def per_day(field: str) -> dict:
    return {
        "label": "Day",
        "customLabel": True,
        "dataType": "date",
        "operationType": "date_histogram",
        "isBucketed": True,
        "scale": "interval",
        "sourceField": field,
        "params": {"interval": "d", "includeEmptyRows": True, "dropPartials": False},
    }


# ------------------------------------------------------------ visualizations
def metric_vis() -> dict:
    return {"layerId": "l", "layerType": "data", "metricAccessor": "m"}


def xy_vis(series: str, accessors: list[str]) -> dict:
    return {
        "legend": {"isVisible": len(accessors) > 1, "position": "bottom"},
        "valueLabels": "hide",
        "preferredSeriesType": series,
        "layers": [
            {
                "layerId": "l",
                "layerType": "data",
                "seriesType": series,
                "xAccessor": "x",
                "accessors": accessors,
            }
        ],
    }


def donut_vis() -> dict:
    return {
        "shape": "donut",
        "layers": [
            {
                "layerId": "l",
                "layerType": "data",
                "primaryGroups": ["x"],
                "metrics": ["m"],
                "numberDisplay": "percent",
                "categoryDisplay": "default",
                "legendDisplay": "default",
                "nestedLegend": False,
            }
        ],
    }


def table_vis(column_ids: list[str]) -> dict:
    return {
        "layerId": "l",
        "layerType": "data",
        "columns": [{"columnId": c} for c in column_ids],
    }


VIS_TYPE = {
    "metric": "lnsMetric",
    "bar": "lnsXY",
    "line": "lnsXY",
    "donut": "lnsPie",
    "table": "lnsDatatable",
}


def lens(  # noqa: PLR0913, PLR0917 - one argument per part of a panel
    lens_id: str,
    title: str,
    view: str,
    kind: str,
    columns: dict[str, dict],
    kql: str = "",
    description: str = "",
) -> dict:
    """A Lens panel. Column ids: "x" = the bucket (terms, day), "m..." = metrics."""
    metrics = [c for c in columns if c != "x"]
    vis = {
        "metric": metric_vis,
        "bar": lambda: xy_vis("bar_horizontal", metrics),
        "line": lambda: xy_vis("line", metrics),
        "donut": donut_vis,
        "table": lambda: table_vis(list(columns)),
    }[kind]()
    return {
        "type": "lens",
        "id": lens_id,
        "attributes": {
            "title": title,
            "description": description,
            "visualizationType": VIS_TYPE[kind],
            "state": {
                "datasourceStates": {
                    "formBased": {
                        "layers": {
                            "l": {
                                "columns": columns,
                                "columnOrder": list(columns),
                                "incompleteColumns": {},
                                "sampling": 1,
                            }
                        }
                    }
                },
                "visualization": vis,
                "query": {"query": kql, "language": "kuery"},
                "filters": [],
                "internalReferences": [],
                "adHocDataViews": {},
            },
        },
        "references": [
            {
                "type": "index-pattern",
                "id": view,
                "name": "indexpattern-datasource-layer-l",
            }
        ],
        "typeMigrationVersion": "8.9.0",
    }


OPEN = "is_open : true"
ABOUT = """**Requester analytics.** A copy of the site's data, refreshed by Logstash
every minute (counts on jobs every night). No names, e-mails or resumes.

* Panels on **jobs and candidates** show *now*; the time picker does not change them.
* Panels on **searches, applications and status changes** follow the time picker.
* Fields and example queries: `docs/analytics.md` in the repository."""

#: (lens object, width, height); laid out left to right on a 48-column grid.
PANELS = [
    (
        lens(
            "rq-open-jobs",
            "Open jobs",
            "requester-postings",
            "metric",
            {"m": count("Open jobs")},
            OPEN,
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-hiring-employers",
            "Companies hiring",
            "requester-postings",
            "metric",
            {"m": metric("unique_count", "employer_id", "Companies hiring")},
            OPEN,
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-open-to-work",
            "Candidates open to work",
            "requester-candidates",
            "metric",
            {"m": count("Open to work")},
            "is_open_to_work : true",
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-searches",
            "Searches",
            "requester-searches",
            "metric",
            {"m": count("Searches")},
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-zero-searches",
            "Searches with no results",
            "requester-searches",
            "metric",
            {"m": count("No results")},
            "zero_results : true",
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-applications",
            "Applications",
            "requester-applications",
            "metric",
            {"m": count("Applications")},
        ),
        8,
        6,
    ),
    (
        lens(
            "rq-searches-per-day",
            "Searches per day",
            "requester-searches",
            "line",
            {
                "x": per_day("created_at"),
                "m": count("Searches"),
                "m2": count("No results", "zero_results : true"),
            },
        ),
        24,
        12,
    ),
    (
        lens(
            "rq-applications-per-day",
            "Applications per day",
            "requester-applications",
            "line",
            {"x": per_day("applied_at"), "m": count("Applications")},
        ),
        24,
        12,
    ),
    (
        lens(
            "rq-top-words",
            "Most searched words",
            "requester-searches",
            "bar",
            {"x": terms("query", "Words", 15), "m": count("Searches")},
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-zero-words",
            "Searched, but no job matched",
            "requester-searches",
            "table",
            {"x": terms("query", "Words", 20), "m": count("Searches")},
            "zero_results : true",
            "Jobs people want that the site does not have yet.",
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-top-search-skills",
            "Most searched skills",
            "requester-searches",
            "bar",
            {"x": terms("skills", "Skill", 15), "m": count("Searches")},
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-skills-demand",
            "Skills open jobs ask for",
            "requester-postings",
            "bar",
            {"x": terms("skills", "Skill", 15), "m": count("Open jobs")},
            OPEN,
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-skills-supply",
            "Skills candidates have",
            "requester-candidates",
            "bar",
            {"x": terms("skills", "Skill", 15), "m": count("Candidates")},
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-search-cities",
            "Most searched cities",
            "requester-searches",
            "bar",
            {"x": terms("location", "City", 10), "m": count("Searches")},
        ),
        16,
        14,
    ),
    (
        lens(
            "rq-jobs-by-city",
            "Open jobs by city",
            "requester-postings",
            "bar",
            {"x": terms("location", "City", 10), "m": count("Open jobs")},
            OPEN,
        ),
        16,
        12,
    ),
    (
        lens(
            "rq-jobs-by-mode",
            "Open jobs by work mode",
            "requester-postings",
            "donut",
            {"x": terms("work_mode", "Work mode", 5), "m": count("Open jobs")},
            OPEN,
        ),
        16,
        12,
    ),
    (
        lens(
            "rq-application-status",
            "Applications by status",
            "requester-applications",
            "donut",
            {"x": terms("status", "Status", 10), "m": count("Applications")},
        ),
        16,
        12,
    ),
    (
        lens(
            "rq-most-applied",
            "Jobs with the most applications",
            "requester-postings",
            "table",
            {
                "x": terms("title", "Job", 10),
                "m": metric("sum", "applications", "Applications"),
                "m2": metric("sum", "saves", "Saved by"),
            },
        ),
        24,
        14,
    ),
    (
        lens(
            "rq-answer-time",
            "Hours until an employer first answers",
            "requester-application-events",
            "metric",
            {"m": metric("median", "hours_since_applied", "Median hours")},
            'from_status : "pending" and actor : "employer"',
            "From applying to the employer's first status change.",
        ),
        12,
        7,
    ),
    (
        lens(
            "rq-accepted",
            "Applications accepted",
            "requester-application-events",
            "metric",
            {"m": count("Accepted")},
            'to_status : "accepted"',
        ),
        12,
        7,
    ),
    (
        lens(
            "rq-open-jobs-over-time",
            "Open jobs and candidates over time",
            "requester-daily-stats",
            "line",
            {
                "x": per_day("day"),
                "m": metric("max", "open_postings", "Open jobs"),
                "m2": metric(
                    "max", "open_to_work_candidates", "Candidates open to work"
                ),
            },
            description="One point per day, from the day analytics was started.",
        ),
        24,
        14,
    ),
]


def about_panel() -> dict:
    return {
        "type": "visualization",
        "id": "rq-about",
        "attributes": {
            "title": "About this dashboard",
            "description": "",
            "visState": json.dumps(
                {
                    "title": "About this dashboard",
                    "type": "markdown",
                    "params": {
                        "markdown": ABOUT,
                        "fontSize": 12,
                        "openLinksInNewTab": False,
                    },
                    "aggs": [],
                }
            ),
            "uiStateJSON": "{}",
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {"query": {"query": "", "language": "kuery"}, "filter": []}
                )
            },
        },
        "references": [],
        "typeMigrationVersion": "8.5.0",
    }


def dashboard(objects: list[tuple[dict, int, int]]) -> dict:
    panels, references = [], []
    x = y = row_height = 0
    for number, (obj, width, height) in enumerate(objects, start=1):
        if x + width > GRID_COLUMNS:
            x, y, row_height = 0, y + row_height, 0
        key = f"p{number}"
        panels.append(
            {
                "type": obj["type"],
                "gridData": {"x": x, "y": y, "w": width, "h": height, "i": key},
                "panelIndex": key,
                "embeddableConfig": {"enhancements": {}},
                "panelRefName": f"panel_{key}",
            }
        )
        references.append(
            {"name": f"{key}:panel_{key}", "type": obj["type"], "id": obj["id"]}
        )
        x += width
        row_height = max(row_height, height)
    return {
        "type": "dashboard",
        "id": "requester-overview",
        "attributes": {
            "title": "Requester: jobs and searches",
            "description": "What candidates search for, which jobs and skills are "
            "in demand, and how applications move.",
            "panelsJSON": json.dumps(panels),
            "optionsJSON": json.dumps(
                {
                    "useMargins": True,
                    "syncColors": False,
                    "syncCursor": True,
                    "syncTooltips": False,
                    "hidePanelTitles": False,
                }
            ),
            "timeRestore": True,
            "timeFrom": "now-30d",
            "timeTo": "now",
            "refreshInterval": {"pause": False, "value": 60_000},
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": json.dumps(
                    {"query": {"query": "", "language": "kuery"}, "filter": []}
                )
            },
        },
        "references": references,
        "typeMigrationVersion": "8.9.0",
    }


def main() -> None:
    about = about_panel()
    layout = [(about, 48, 8), *PANELS]
    objects = [data_view(v) for v in DATA_VIEWS]
    objects += [obj for obj, _w, _h in layout]
    objects.append(dashboard(layout))
    OUT.write_text("".join(json.dumps(o) + "\n" for o in objects), encoding="utf-8")
    print(f"Wrote {len(objects)} saved objects to {OUT}")


if __name__ == "__main__":
    main()
