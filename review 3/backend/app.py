"""
Flask application for the Railway Ticket Reservation & Journey Management
System (DBMS Project 17, Review 3).

Serves the existing review 3/app.html UI unchanged and exposes a JSON API
that the page's JavaScript calls for every real operation (search, booking,
waitlist, cancellation, promotion, fare calculation, CRUD, reports). All
database access goes through booking_service.py.

Run:
    py app.py
"""
import os
import traceback

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import booking_service as svc
from db import AppError

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../review 3

app = Flask(__name__, static_folder=None)


@app.errorhandler(AppError)
def handle_app_error(e):
    return jsonify({"error": e.message}), e.status


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    # Let Flask/Werkzeug's own routing errors (404, 405, ...) through with
    # their real status instead of masking them as a 500.
    return jsonify({"error": e.description}), e.code


@app.errorhandler(Exception)
def handle_unexpected(e):
    traceback.print_exc()
    return jsonify({"error": "Unexpected server error: " + str(e)}), 500


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(APP_ROOT, "app.html")


@app.route("/favicon.ico")
def favicon():
    return "", 204


# ---------------------------------------------------------------------------
# Reference data / dashboard
# ---------------------------------------------------------------------------
@app.route("/api/bootstrap")
def api_bootstrap():
    return jsonify(svc.get_bootstrap())


@app.route("/api/dashboard")
def api_dashboard():
    return jsonify(svc.get_dashboard())


@app.route("/api/counts")
def api_counts():
    return jsonify(svc.get_counts())


# ---------------------------------------------------------------------------
# Search / availability / fare
# ---------------------------------------------------------------------------
@app.route("/api/search")
def api_search():
    from_id = request.args.get("from", type=int)
    to_id = request.args.get("to", type=int)
    journey_date = request.args.get("date")
    cls = request.args.get("cls", "ALL")
    if not from_id or not to_id or not journey_date:
        raise AppError("from, to and date are required", 400)
    return jsonify({"results": svc.search_trains(from_id, to_id, journey_date, cls)})


@app.route("/api/availability")
def api_availability():
    train_id = request.args.get("trainId", type=int)
    coach_id = request.args.get("coachId", type=int)
    src_id = request.args.get("src", type=int)
    dest_id = request.args.get("dest", type=int)
    journey_date = request.args.get("date")
    if not all([train_id, coach_id, src_id, dest_id, journey_date]):
        raise AppError("trainId, coachId, src, dest and date are required", 400)
    return jsonify(svc.get_availability(train_id, coach_id, src_id, dest_id, journey_date))


@app.route("/api/fare")
def api_fare():
    train_id = request.args.get("trainId", type=int)
    src_id = request.args.get("src", type=int)
    dest_id = request.args.get("dest", type=int)
    coach_type = request.args.get("coachType")
    age = request.args.get("age", default=30, type=int)
    quota = request.args.get("quota", default="GN")
    if not all([train_id, src_id, dest_id, coach_type]):
        raise AppError("trainId, src, dest and coachType are required", 400)
    return jsonify(svc.get_fare_quote(train_id, src_id, dest_id, coach_type, age, quota))


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
@app.route("/api/bookings", methods=["GET", "POST"])
def api_bookings():
    if request.method == "POST":
        return jsonify(svc.book_ticket(request.get_json(force=True, silent=True) or {})), 201
    status = request.args.get("status")
    return jsonify({"bookings": svc.list_bookings(status)})


@app.route("/api/bookings/<int:pnr>")
def api_booking_detail(pnr):
    return jsonify(svc.get_booking(pnr))


@app.route("/api/bookings/<int:pnr>/preview-cancel")
def api_preview_cancel(pnr):
    return jsonify(svc.preview_cancel(pnr))


@app.route("/api/bookings/<int:pnr>/cancel", methods=["POST"])
def api_cancel_booking(pnr):
    return jsonify(svc.cancel_booking(pnr))


# ---------------------------------------------------------------------------
# Waitlist
# ---------------------------------------------------------------------------
@app.route("/api/waitlist")
def api_waitlist():
    return jsonify(svc.list_waitlist())


@app.route("/api/waitlist/<int:wl_id>/promote", methods=["POST"])
def api_promote_one(wl_id):
    return jsonify(svc.promote_one(wl_id))


@app.route("/api/waitlist/promote-all", methods=["POST"])
def api_promote_all():
    return jsonify(svc.promote_all())


@app.route("/api/waitlist/<int:wl_id>/cancel", methods=["POST"])
def api_cancel_waitlist(wl_id):
    return jsonify(svc.cancel_waitlist_entry(wl_id))


# ---------------------------------------------------------------------------
# CRUD manager
# ---------------------------------------------------------------------------
@app.route("/api/trains", methods=["GET", "POST"])
def api_trains():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(svc.create_train(body.get("name"), body.get("type"))), 201
    return jsonify({"trains": svc.list_trains()})


@app.route("/api/trains/<int:train_id>", methods=["PUT", "DELETE"])
def api_train_detail(train_id):
    if request.method == "DELETE":
        svc.delete_train(train_id)
        return jsonify({"ok": True})
    body = request.get_json(force=True, silent=True) or {}
    return jsonify(svc.update_train(train_id, body.get("name"), body.get("type")))


@app.route("/api/stations", methods=["GET", "POST"])
def api_stations():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(svc.create_station(body.get("code"), body.get("name"), body.get("city"), body.get("zone"))), 201
    return jsonify({"stations": svc.list_stations()})


@app.route("/api/stations/<int:station_id>", methods=["DELETE"])
def api_station_detail(station_id):
    svc.delete_station(station_id)
    return jsonify({"ok": True})


@app.route("/api/passengers", methods=["GET", "POST"])
def api_passengers():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(svc.create_passenger(body.get("fname"), body.get("lname"), body.get("age"), body.get("gender"))), 201
    return jsonify({"passengers": svc.list_passengers()})


@app.route("/api/passengers/<int:passenger_id>", methods=["DELETE"])
def api_passenger_detail(passenger_id):
    svc.delete_passenger(passenger_id)
    return jsonify({"ok": True})


@app.route("/api/schedules", methods=["GET", "POST"])
def api_schedules():
    if request.method == "POST":
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(svc.create_schedule(body.get("trainId"), body.get("date"))), 201
    return jsonify({"schedules": svc.list_schedules()})


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@app.route("/api/reports/occupancy")
def api_report_occupancy():
    return jsonify({"rows": svc.report_occupancy()})


@app.route("/api/reports/revenue")
def api_report_revenue():
    return jsonify({"rows": svc.report_revenue()})


@app.route("/api/reports/segments")
def api_report_segments():
    return jsonify({"rows": svc.report_segments()})


@app.route("/api/reports/passengers")
def api_report_passengers():
    return jsonify({"rows": svc.report_passengers()})


@app.route("/api/reports/summary")
def api_report_summary():
    return jsonify(svc.report_summary())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
