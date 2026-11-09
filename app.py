import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from secrets import compare_digest, token_urlsafe

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from pymysql.err import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from access import admin_required, login_required
from campus import campus
from db import close_db, execute, fetch_all, fetch_one, get_db
from planner import (
    BUCHAREST, CLASS_TYPES, DAYS, TASK_TYPES, find_overlap, next_class, ora_text, upcoming_alerts,
)

app = Flask(__name__)
app.register_blueprint(campus)
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_NAME="campusos_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=32 * 1024,
)
if len(app.secret_key) < 32:
    raise RuntimeError("SECRET_KEY trebuie să aibă cel puțin 32 de caractere.")

app.teardown_appcontext(close_db)
app.add_template_filter(ora_text)
CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


def valid_email(email):
    return len(email) <= 254 and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)


def valid_password(password):
    return 8 <= len(password) <= 128


@app.cli.command("init-db")
def init_db():
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    for statement in schema.split(";"):
        if statement.strip():
            execute(statement)
    get_db().commit()


@app.cli.command("init-admin")
def init_admin():
    email = os.environ.get("ADMIN_EMAIL", "admin@campusos.local").strip().lower()
    password = os.environ["ADMIN_PASSWORD"]
    if not valid_email(email) or not valid_password(password):
        raise click.ClickException("Verifică e-mailul și parola de 8–128 de caractere pentru admin.")
    admin = fetch_one("SELECT id, email FROM users WHERE role = 'admin' LIMIT 1")
    if admin:
        if admin["email"] != email:
            raise click.ClickException("Folosește adresa ADMIN_EMAIL aleasă la prima pornire.")
        return
    try:
        execute(
            "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'admin')",
            (email, generate_password_hash(password)),
        )
        get_db().commit()
    except IntegrityError as error:
        get_db().rollback()
        raise click.ClickException("Adresa de admin este deja folosită de un cont existent.") from error


@app.before_request
def load_user():
    g.user = None
    if request.endpoint == "static":
        return
    if request.method == "POST":
        expected = session.get("csrf", "")
        supplied = request.form.get("csrf", "")
        if not expected or not compare_digest(expected.encode(), supplied.encode()):
            abort(400, "Formularul a expirat. Reîncarcă pagina și încearcă din nou.")
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = fetch_one("SELECT id, email, role FROM users WHERE id = %s", (user_id,))


@app.context_processor
def template_values():
    if "csrf" not in session:
        session["csrf"] = token_urlsafe(24)
    return {"csrf": session["csrf"], "class_types": CLASS_TYPES, "task_types": TASK_TYPES}


@app.route("/autentificare", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = fetch_one("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        if user and valid_password(password) and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("E-mailul sau parola sunt greșite.", "error")
    return render_template("auth.html", register=False)


@app.route("/cont-nou", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not valid_email(email) or not valid_password(password):
            flash("Introdu un e-mail valid și o parolă de 8–128 de caractere.", "error")
        else:
            try:
                execute(
                    "INSERT INTO users (email, password_hash) VALUES (%s, %s)",
                    (email, generate_password_hash(password)),
                )
                get_db().commit()
            except IntegrityError:
                get_db().rollback()
                flash("Există deja un cont cu această adresă.", "error")
            else:
                flash("Contul a fost creat. Acum te poți autentifica.", "success")
                return redirect(url_for("login"))
    return render_template("auth.html", register=True)


@app.post("/iesire")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def dashboard():
    now = datetime.now(BUCHAREST)
    classes = fetch_all("SELECT * FROM schedule ORDER BY weekday, starts_at")
    tasks = fetch_all(
        "SELECT * FROM tasks WHERE user_id = %s ORDER BY due_date, due_time, id",
        (g.user["id"],),
    )
    when, lesson = next_class(classes, now)
    exam = next(
        (item for item in tasks if item["kind"] == "examen" and item["due_date"] >= now.date()),
        None,
    )
    deadlines = [
        item for item in tasks
        if item["kind"] == "termen" and not item["done"] and item["due_date"] >= now.date()
    ][:3]
    return render_template(
        "dashboard.html", lesson=lesson, when=when, exam=exam, deadlines=deadlines,
        alerts=upcoming_alerts(tasks, now.date()),
    )


@app.get("/orar")
@login_required
def schedule():
    today = datetime.now(BUCHAREST).date()
    offset = request.args.get("saptamana", default=0, type=int)
    if not -520 <= offset <= 520:
        abort(404)
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    sunday = monday + timedelta(days=6)
    lessons = fetch_all("SELECT * FROM schedule ORDER BY weekday, starts_at")
    exams = fetch_all(
        """SELECT * FROM tasks WHERE user_id = %s AND kind = 'examen'
           AND due_date BETWEEN %s AND %s ORDER BY due_date, due_time, id""",
        (g.user["id"], monday, sunday),
    )
    days = []
    for index, label in enumerate(DAYS):
        day = monday + timedelta(days=index)
        days.append({
            "label": label,
            "date": day,
            "lessons": [item for item in lessons if item["weekday"] == index],
            "exams": [item for item in exams if item["due_date"] == day],
        })
    return render_template("schedule.html", days=days, monday=monday, sunday=sunday, offset=offset)


@app.route("/orar/adauga", methods=["GET", "POST"])
@app.route("/orar/<int:entry_id>/editeaza", methods=["GET", "POST"])
@admin_required
def edit_schedule(entry_id=None):
    entry = {}
    if entry_id is not None:
        entry = fetch_one("SELECT * FROM schedule WHERE id = %s", (entry_id,))
        if entry is None:
            abort(404)
    if request.method == "POST":
        entry = request.form
        title = entry.get("title", "").strip()
        kind = entry.get("kind")
        weekday = entry.get("weekday", type=int)
        start = entry.get("starts_at", "")
        end = entry.get("ends_at", "")
        room = entry.get("room", "").strip()
        if (
            not 1 <= len(title) <= 100 or kind not in CLASS_TYPES or weekday not in range(7)
            or not CLOCK.fullmatch(start) or not CLOCK.fullmatch(end)
            or end <= start or len(room) > 60
        ):
            flash("Verifică materia, ziua și intervalul. Ora de final trebuie să fie după ora de început.", "error")
        else:
            # Blocăm rândul adminului ca două salvări să nu treacă de verificare în același timp.
            fetch_one("SELECT id FROM users WHERE id = %s FOR UPDATE", (g.user["id"],))
            if entry_id is not None and fetch_one(
                "SELECT id FROM schedule WHERE id = %s FOR UPDATE", (entry_id,),
            ) is None:
                abort(404)
            same_day = fetch_all(
                """SELECT title, starts_at, ends_at FROM schedule
                   WHERE weekday = %s AND id <> %s FOR UPDATE""",
                (weekday, entry_id or 0),
            )
            conflict = find_overlap(same_day, start, end)
            if conflict:
                get_db().rollback()
                flash(f"Intervalul se suprapune cu {conflict['title']}.", "error")
            else:
                values = (title, kind, weekday, start, end, room)
                if entry_id is None:
                    execute(
                        """INSERT INTO schedule (title, kind, weekday, starts_at, ends_at, room)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        values,
                    )
                else:
                    execute(
                        """UPDATE schedule SET title = %s, kind = %s, weekday = %s, starts_at = %s,
                           ends_at = %s, room = %s WHERE id = %s""",
                        (*values, entry_id),
                    )
                get_db().commit()
                flash("Ora a fost salvată în orarul comun.", "success")
                return redirect(url_for("schedule"))
    return render_template("schedule_form.html", entry=entry, entry_id=entry_id, days=DAYS)


@app.post("/orar/<int:entry_id>/sterge")
@admin_required
def delete_schedule(entry_id):
    fetch_one("SELECT id FROM users WHERE id = %s FOR UPDATE", (g.user["id"],))
    execute("DELETE FROM schedule WHERE id = %s", (entry_id,))
    get_db().commit()
    flash("Ora a fost ștearsă din orarul comun.", "success")
    return redirect(url_for("schedule"))


@app.get("/activitati")
@login_required
def tasks():
    items = fetch_all(
        "SELECT * FROM tasks WHERE user_id = %s ORDER BY due_date, due_time, id",
        (g.user["id"],),
    )
    exams = [item for item in items if item["kind"] == "examen"]
    deadlines = [item for item in items if item["kind"] == "termen"]
    return render_template("tasks.html", exams=exams, deadlines=deadlines)


def own_task(task_id):
    task = fetch_one("SELECT * FROM tasks WHERE id = %s AND user_id = %s", (task_id, g.user["id"]))
    if task is None:
        abort(404)
    return task


@app.route("/activitati/adauga", methods=["GET", "POST"])
@app.route("/activitati/<int:task_id>/editeaza", methods=["GET", "POST"])
@login_required
def edit_task(task_id=None):
    entry = own_task(task_id) if task_id is not None else {"kind": request.args.get("tip", "examen")}
    if request.method == "POST":
        entry = request.form
        title = entry.get("title", "").strip()
        kind = entry.get("kind")
        raw_date = entry.get("due_date", "")
        due_time = entry.get("due_time", "")
        try:
            due = date.fromisoformat(raw_date)
        except ValueError:
            due = None
        if (
            not 1 <= len(title) <= 100 or kind not in TASK_TYPES or not due or due.year < 1000
            or (due_time and not CLOCK.fullmatch(due_time))
        ):
            flash("Completează un titlu, un tip și o dată validă.", "error")
        else:
            values = (kind, title, due, due_time or None)
            if task_id is None:
                execute(
                    "INSERT INTO tasks (kind, title, due_date, due_time, user_id) VALUES (%s, %s, %s, %s, %s)",
                    (*values, g.user["id"]),
                )
            else:
                execute(
                    """UPDATE tasks SET kind = %s, title = %s, due_date = %s, due_time = %s,
                       done = IF(%s = 'examen', FALSE, done) WHERE id = %s AND user_id = %s""",
                    (*values, kind, task_id, g.user["id"]),
                )
            get_db().commit()
            flash("Activitatea a fost salvată.", "success")
            return redirect(url_for("tasks"))
    return render_template("task_form.html", entry=entry, task_id=task_id)


@app.post("/activitati/<int:task_id>/stare")
@login_required
def set_task_status(task_id):
    if own_task(task_id)["kind"] != "termen":
        abort(404)
    done = request.form.get("done")
    if done not in {"0", "1"}:
        abort(400)
    execute(
        "UPDATE tasks SET done = %s WHERE id = %s AND user_id = %s AND kind = 'termen'",
        (int(done), task_id, g.user["id"]),
    )
    get_db().commit()
    return redirect(url_for("tasks"))


@app.post("/activitati/<int:task_id>/sterge")
@login_required
def delete_task(task_id):
    own_task(task_id)
    execute("DELETE FROM tasks WHERE id = %s AND user_id = %s", (task_id, g.user["id"]))
    get_db().commit()
    flash("Activitatea a fost ștearsă.", "success")
    return redirect(url_for("tasks"))
