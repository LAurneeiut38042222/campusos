from functools import wraps

from flask import abort, g, redirect, url_for


def login_required(view):
    @wraps(view)
    def check(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return check


def admin_required(view):
    @wraps(view)
    @login_required
    def check(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return check
