from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

BUCHAREST = ZoneInfo("Europe/Bucharest")
DAYS = ("Luni", "Marți", "Miercuri", "Joi", "Vineri", "Sâmbătă", "Duminică")
CLASS_TYPES = {"curs": "Curs", "seminar": "Seminar", "laborator": "Laborator"}
TASK_TYPES = {"examen": "Examen", "termen": "Termen"}


def ora_text(value):
    if isinstance(value, timedelta):
        hours, seconds = divmod(int(value.total_seconds()), 3600)
        return f"{hours:02d}:{seconds // 60:02d}"
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return value or ""


def find_overlap(lessons, start, end):
    for lesson in lessons:
        if start < ora_text(lesson["ends_at"]) and end > ora_text(lesson["starts_at"]):
            return lesson
    return None


def next_class(classes, now):
    upcoming = []
    for item in classes:
        days_ahead = (item["weekday"] - now.weekday()) % 7
        starts = time.fromisoformat(ora_text(item["starts_at"]))
        when = datetime.combine(now.date() + timedelta(days=days_ahead), starts, now.tzinfo)
        if when < now:
            when += timedelta(days=7)
        upcoming.append((when, item))
    return min(upcoming, key=lambda pair: pair[0], default=(None, None))


def upcoming_alerts(tasks, today):
    alerts = []
    for item in tasks:
        days = (item["due_date"] - today).days
        if item["kind"] == "examen" and 0 <= days <= 7:
            alerts.append((item, "Examen apropiat"))
        elif item["kind"] == "termen" and not item["done"] and -7 <= days <= 3:
            message = "Termen depășit" if days < 0 else "Termen apropiat"
            alerts.append((item, message))
    return alerts
