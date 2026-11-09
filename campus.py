from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from pymysql.err import IntegrityError

from access import admin_required, login_required
from db import execute, fetch_all, fetch_one, get_db
from planner import BUCHAREST

campus = Blueprint("campus", __name__)
LAUNDRY_HOURS = (8, 10, 12, 14, 16, 18, 20)


def students():
    return fetch_all("SELECT id, email FROM users WHERE role = 'student' ORDER BY email")


def selected_student():
    student_id = request.form.get("student", type=int)
    return fetch_one("SELECT id FROM users WHERE id = %s AND role = 'student'", (student_id,))


def decimal_value(field, minimum, maximum):
    try:
        value = Decimal(request.form.get(field, "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    if value.is_finite() and minimum <= value <= maximum and value == value.quantize(Decimal("0.01")):
        return value
    return None


@campus.get("/camin")
@login_required
def dorm():
    if g.user["role"] == "admin":
        fees = fetch_all(
            """SELECT dorm_fees.*, users.email FROM dorm_fees JOIN users ON users.id = dorm_fees.user_id
               ORDER BY billing_month DESC, users.email"""
        )
        return render_template("dorm.html", fees=fees, students=students())
    fees = fetch_all(
        "SELECT * FROM dorm_fees WHERE user_id = %s ORDER BY billing_month DESC",
        (g.user["id"],),
    )
    return render_template("dorm.html", fees=fees)


@campus.post("/camin/adauga")
@admin_required
def add_fee():
    student = selected_student()
    amount = decimal_value("amount", Decimal("0.01"), Decimal("9999999.99"))
    try:
        month = date.fromisoformat(request.form.get("month", "") + "-01")
    except ValueError:
        month = None
    if student is None or amount is None or month is None or month.year < 1000:
        flash("Alege studentul, luna și o sumă validă în lei.", "error")
        return redirect(url_for("campus.dorm"))
    try:
        execute(
            "INSERT INTO dorm_fees (user_id, billing_month, amount) VALUES (%s, %s, %s)",
            (student["id"], month, amount),
        )
        get_db().commit()
    except IntegrityError as error:
        if error.args[0] != 1062:
            raise
        get_db().rollback()
        flash("Studentul are deja o taxă pentru luna aleasă.", "error")
    else:
        flash("Taxa a fost adăugată.", "success")
    return redirect(url_for("campus.dorm"))


@campus.post("/camin/<int:fee_id>/simuleaza")
@login_required
def pay_demo(fee_id):
    if g.user["role"] != "student":
        abort(403)
    fee = fetch_one("SELECT id FROM dorm_fees WHERE id = %s AND user_id = %s", (fee_id, g.user["id"]))
    if fee is None:
        abort(404)
    execute(
        """UPDATE dorm_fees SET demo_paid_at = COALESCE(demo_paid_at, UTC_TIMESTAMP())
           WHERE id = %s AND user_id = %s""",
        (fee_id, g.user["id"]),
    )
    get_db().commit()
    flash("Simularea a fost înregistrată. Nu s-au transferat bani.", "success")
    return redirect(url_for("campus.dorm"))


@campus.get("/spalatorie")
@login_required
def laundry():
    now = datetime.now(BUCHAREST)
    days = [now.date() + timedelta(days=index) for index in range(7)]
    try:
        selected = date.fromisoformat(request.args.get("zi", days[0].isoformat()))
    except ValueError:
        abort(404)
    if selected not in days:
        abort(404)
    bookings = fetch_all(
        "SELECT id, user_id, slot_hour FROM laundry_bookings WHERE booking_date = %s",
        (selected,),
    )
    occupied = {item["slot_hour"]: item for item in bookings}
    slots = []
    for hour in LAUNDRY_HOURS:
        booking = occupied.get(hour)
        slots.append({
            "hour": hour,
            "past": now >= datetime(selected.year, selected.month, selected.day, hour, tzinfo=BUCHAREST),
            "occupied": booking is not None,
            "mine": booking is not None and booking["user_id"] == g.user["id"],
            "id": booking["id"] if booking else None,
        })
    return render_template("laundry.html", days=days, selected=selected, slots=slots)


@campus.post("/spalatorie/rezerva")
@login_required
def book_laundry():
    if g.user["role"] != "student":
        abort(403)
    now = datetime.now(BUCHAREST)
    try:
        selected = date.fromisoformat(request.form.get("day", ""))
    except ValueError:
        abort(400)
    hour = request.form.get("hour", type=int)
    if hour not in LAUNDRY_HOURS or not 0 <= (selected - now.date()).days < 7:
        abort(400)
    if now >= datetime(selected.year, selected.month, selected.day, hour, tzinfo=BUCHAREST):
        flash("Intervalul a început deja.", "error")
        return redirect(url_for("campus.laundry", zi=selected.isoformat()))
    try:
        execute(
            "INSERT INTO laundry_bookings (user_id, booking_date, slot_hour) VALUES (%s, %s, %s)",
            (g.user["id"], selected, hour),
        )
        get_db().commit()
    except IntegrityError as error:
        if error.args[0] != 1062:
            raise
        get_db().rollback()
        flash("Intervalul a fost rezervat între timp.", "error")
    else:
        flash("Programarea a fost salvată.", "success")
    return redirect(url_for("campus.laundry", zi=selected.isoformat()))


@campus.post("/spalatorie/<int:booking_id>/anuleaza")
@login_required
def cancel_laundry(booking_id):
    booking = fetch_one(
        "SELECT booking_date, slot_hour FROM laundry_bookings WHERE id = %s AND user_id = %s",
        (booking_id, g.user["id"]),
    )
    if booking is None:
        abort(404)
    selected = booking["booking_date"]
    if datetime.now(BUCHAREST) >= datetime(
        selected.year, selected.month, selected.day, booking["slot_hour"], tzinfo=BUCHAREST,
    ):
        flash("Intervalul a început deja.", "error")
        return redirect(url_for("campus.laundry"))
    execute("DELETE FROM laundry_bookings WHERE id = %s AND user_id = %s", (booking_id, g.user["id"]))
    get_db().commit()
    flash("Programarea a fost anulată.", "success")
    return redirect(url_for("campus.laundry", zi=selected.isoformat()))


@campus.get("/note")
@login_required
def grades():
    if g.user["role"] == "admin":
        results = fetch_all(
            """SELECT grades.*, users.email FROM grades JOIN users ON users.id = grades.user_id
               ORDER BY users.email, grades.subject"""
        )
        return render_template("grades.html", results=results, students=students())
    results = fetch_all(
        "SELECT subject, grade FROM grades WHERE user_id = %s ORDER BY subject",
        (g.user["id"],),
    )
    return render_template("grades.html", results=results)


@campus.post("/note/salveaza")
@admin_required
def save_grade():
    student = selected_student()
    subject = request.form.get("subject", "").strip()
    grade = decimal_value("grade", Decimal("1"), Decimal("10"))
    if student is None or not 1 <= len(subject) <= 100 or grade is None:
        flash("Alege studentul, materia și o notă între 1 și 10.", "error")
    else:
        execute(
            """INSERT INTO grades (user_id, subject, grade) VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE grade = %s""",
            (student["id"], subject, grade, grade),
        )
        get_db().commit()
        flash("Nota a fost salvată.", "success")
    return redirect(url_for("campus.grades"))
