"""
Review 3 database setup script.

Runs schema.sql (drops & recreates RailwayReservationDB) and then populates
it with realistic reference data (stations, trains, routes, coaches, seats)
plus sample transactional data (passengers, bookings, journey segments,
waitlist, payments) so the app has something to search, book against and
report on the moment it starts.

Usage:
    py database/seed.py

Reads connection settings from environment variables (see config below).
RAILWAY_DB_PASSWORD is required and is never hardcoded here.
"""
import os
import sys
from datetime import date, timedelta

import mysql.connector

HOST = os.environ.get("RAILWAY_DB_HOST", "127.0.0.1")
PORT = int(os.environ.get("RAILWAY_DB_PORT", "3306"))
USER = os.environ.get("RAILWAY_DB_USER", "root")
PASSWORD = os.environ.get("RAILWAY_DB_PASSWORD")
DB_NAME = "RailwayReservationDB"

if not PASSWORD:
    print("ERROR: set RAILWAY_DB_PASSWORD in the environment before running this script.")
    sys.exit(1)

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def _strip_line_comments(sql_text):
    # Drop full-line "-- ..." comments before naively splitting on ';', since
    # a comment's prose (e.g. "PROMOTED/CANCELLED); MySQL allows ...") can
    # itself contain a semicolon and would otherwise corrupt the split.
    kept = [ln for ln in sql_text.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(kept)


def run_schema(cnx):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        sql_text = f.read()

    # Split on DELIMITER blocks so the trigger body (which itself contains
    # semicolons) is sent to the server as one statement, like a DBA would
    # via the MySQL CLI.
    cur = cnx.cursor()
    parts = sql_text.split("DELIMITER //")
    head, rest = parts[0], parts[1] if len(parts) > 1 else ""
    for stmt in [s.strip() for s in _strip_line_comments(head).split(";") if s.strip()]:
        cur.execute(stmt)

    if rest:
        trigger_body, _, tail = rest.partition("DELIMITER ;")
        trigger_sql = _strip_line_comments(trigger_body.replace("//", "")).strip()
        cur.execute(trigger_sql)
        for stmt in [s.strip() for s in _strip_line_comments(tail).split(";") if s.strip()]:
            cur.execute(stmt)
    cnx.commit()
    cur.close()
    print("Schema created.")


# Berth layout for a standard 8-berth AC 3-Tier / Sleeper bay
BAY_3TIER = ["Lower", "Middle", "Upper", "Lower", "Middle", "Upper", "Side Lower", "Side Upper"]
BAY_2TIER = ["Lower", "Upper", "Lower", "Upper"]
BAY_CHAIR = ["Window", "Aisle", "Middle", "Aisle", "Window"]


def berth_for(coach_type, seat_number):
    t = coach_type.lower()
    if "1st" in t or "cabin" in t:
        return "Cabin"
    if "3-tier" in t or "sleeper" in t:
        return BAY_3TIER[(seat_number - 1) % len(BAY_3TIER)]
    if "2-tier" in t:
        return BAY_2TIER[(seat_number - 1) % len(BAY_2TIER)]
    return BAY_CHAIR[(seat_number - 1) % len(BAY_CHAIR)]


def seed_data(cnx):
    cur = cnx.cursor()

    # ---- Stations ----
    stations = [
        ("NDLS", "New Delhi", "Delhi", "NR"),
        ("CNB", "Kanpur Central", "Kanpur", "NCR"),
        ("PRYJ", "Prayagraj Junction", "Prayagraj", "NCR"),
        ("HWH", "Howrah Junction", "Kolkata", "ER"),
        ("CSTM", "Mumbai CSMT", "Mumbai", "CR"),
        ("PUNE", "Pune Junction", "Pune", "CR"),
    ]
    cur.executemany(
        "INSERT INTO Station (Code, Name, City, Zone) VALUES (%s,%s,%s,%s)", stations
    )

    # ---- Trains ----
    trains = [
        ("Rajdhani Express", "Superfast Express"),
        ("Vande Bharat Express", "Semi-High Speed"),
        ("Duronto Express", "Non-Stop Superfast"),
    ]
    cur.executemany("INSERT INTO Train (Name, Type) VALUES (%s,%s)", trains)
    cnx.commit()

    station_id = {code: i + 1 for i, (code, *_ ) in enumerate(stations)}
    train_id = {name: i + 1 for i, (name, _t) in enumerate(trains)}

    # ---- Route stops ----
    # (train, station_code, seq, arr, dep, dist_km)
    route_rows = [
        (train_id["Rajdhani Express"], "NDLS", 1, None, "16:55:00", 0),
        (train_id["Rajdhani Express"], "CNB", 2, "21:30:00", "21:35:00", 440),
        (train_id["Rajdhani Express"], "PRYJ", 3, "23:45:00", "23:50:00", 635),
        (train_id["Rajdhani Express"], "HWH", 4, "09:55:00", None, 1445),
        (train_id["Vande Bharat Express"], "CSTM", 1, None, "06:05:00", 0),
        (train_id["Vande Bharat Express"], "PUNE", 2, "09:15:00", None, 192),
        (train_id["Duronto Express"], "NDLS", 1, None, "08:05:00", 0),
        (train_id["Duronto Express"], "HWH", 2, "22:30:00", None, 1530),
    ]
    cur.executemany(
        "INSERT INTO Route_Stop (TrainID, StationID, StopSequence, ArrivalTime, DepartureTime, Distance) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        [(t, station_id[code], seq, arr, dep, dist) for t, code, seq, arr, dep, dist in route_rows],
    )
    cnx.commit()

    cur.execute("SELECT RouteID, TrainID, StationID, StopSequence FROM Route_Stop")
    route_lookup = {}  # (trainId, stationId) -> routeId
    for route_id, t_id, s_id, seq in cur.fetchall():
        route_lookup[(t_id, s_id)] = route_id

    # ---- Schedules (several upcoming journey dates per train) ----
    today = date.today()
    schedule_rows = []
    for t_name, t_id in train_id.items():
        for offset in (1, 2, 8, 15):
            schedule_rows.append((t_id, today + timedelta(days=offset)))
    cur.executemany(
        "INSERT INTO Schedule (TrainID, JourneyDate) VALUES (%s,%s)", schedule_rows
    )
    cnx.commit()

    cur.execute("SELECT ScheduleID, TrainID, JourneyDate FROM Schedule")
    schedules = cur.fetchall()
    schedule_id = {}  # (trainId, isoDate) -> scheduleId
    for sid, tid, jd in schedules:
        schedule_id[(tid, jd.isoformat())] = sid

    # ---- Coaches ----
    coach_rows = [
        (train_id["Rajdhani Express"], "AC 3-Tier", 24),
        (train_id["Rajdhani Express"], "AC 1st Class", 8),
        (train_id["Rajdhani Express"], "Sleeper", 32),
        (train_id["Vande Bharat Express"], "Executive Chair", 20),
        (train_id["Vande Bharat Express"], "AC 2-Tier", 16),
        (train_id["Duronto Express"], "AC 2-Tier", 16),
        (train_id["Duronto Express"], "Sleeper", 36),
    ]
    cur.executemany(
        "INSERT INTO Coach (TrainID, CoachType, TotalSeats) VALUES (%s,%s,%s)", coach_rows
    )
    cnx.commit()

    cur.execute("SELECT CoachID, TrainID, CoachType, TotalSeats FROM Coach")
    coaches = cur.fetchall()

    # ---- Seats (generated per coach) ----
    seat_rows = []
    for coach_id, t_id, coach_type, total_seats in coaches:
        for n in range(1, total_seats + 1):
            seat_rows.append((coach_id, n, berth_for(coach_type, n)))
    cur.executemany(
        "INSERT INTO Seat (CoachID, SeatNumber, BerthType) VALUES (%s,%s,%s)", seat_rows
    )
    cnx.commit()

    cur.execute("SELECT SeatID, CoachID, SeatNumber FROM Seat")
    seat_lookup = {}  # (coachId, seatNumber) -> seatId
    for seat_id, coach_id, seat_number in cur.fetchall():
        seat_lookup[(coach_id, seat_number)] = seat_id

    coach_by_type = {}  # (trainId, coachType) -> coachId
    for coach_id, t_id, coach_type, total_seats in coaches:
        coach_by_type[(t_id, coach_type)] = coach_id

    # ---- Passengers ----
    passengers = [
        ("Aarav", "Sharma", 28, "Male"),
        ("Priya", "Verma", 25, "Female"),
        ("Rohan", "Gupta", 34, "Male"),
        ("Siddharth", "Rao", 24, "Male"),
        ("Ananya", "Sen", 29, "Female"),
        ("Rahul", "Roy", 42, "Male"),
        ("Kavya", "Iyer", 31, "Female"),
        ("Vikram", "Nair", 55, "Male"),
    ]
    cur.executemany(
        "INSERT INTO Passenger (FirstName, LastName, Age, Gender) VALUES (%s,%s,%s,%s)",
        passengers,
    )
    cnx.commit()
    cur.execute("SELECT PassengerID, FirstName, LastName FROM Passenger")
    passenger_id = {(f, l): pid for pid, f, l in cur.fetchall()}

    # ---- Sample bookings + segments + a waitlist entry + payments ----
    raj_sched1 = schedule_id[(train_id["Rajdhani Express"], (today + timedelta(days=1)).isoformat())]
    ac3 = coach_by_type[(train_id["Rajdhani Express"], "AC 3-Tier")]
    seat_ac3_1 = seat_lookup[(ac3, 1)]

    def insert_booking(passenger_key, fare, status, booking_date):
        pid = passenger_id[passenger_key]
        cur.execute(
            "INSERT INTO Booking (PassengerID, BookingDate, TotalFare, Status) VALUES (%s,%s,%s,%s)",
            (pid, booking_date, fare, status),
        )
        return cur.lastrowid

    ndls = route_lookup[(train_id["Rajdhani Express"], station_id["NDLS"])]
    cnb = route_lookup[(train_id["Rajdhani Express"], station_id["CNB"])]
    hwh = route_lookup[(train_id["Rajdhani Express"], station_id["HWH"])]

    pnr1 = insert_booking(("Aarav", "Sharma"), 1500.00, "CONFIRMED", today)
    cur.execute(
        "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
        "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
        (pnr1, raj_sched1, ndls, cnb, seat_ac3_1),
    )
    cnx.commit()

    pnr2 = insert_booking(("Rohan", "Gupta"), 1800.00, "CONFIRMED", today)
    cur.execute(
        "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
        "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
        (pnr2, raj_sched1, cnb, hwh, seat_ac3_1),
    )
    cnx.commit()

    pnr3 = insert_booking(("Priya", "Verma"), 3200.00, "WAITLISTED", today)
    cur.execute(
        "INSERT INTO Waitlist (PNRID, ScheduleID, RequestedCoachID, SourceRouteID, DestRouteID, Position, Status) "
        "VALUES (%s,%s,%s,%s,%s,1,'WAITING')",
        (pnr3, raj_sched1, ac3, ndls, hwh),
    )
    cnx.commit()

    ac1 = coach_by_type[(train_id["Rajdhani Express"], "AC 1st Class")]
    seat_ac1_1 = seat_lookup[(ac1, 1)]
    pnr4 = insert_booking(("Rahul", "Roy"), 1800.00, "CANCELLED", today - timedelta(days=1))
    cur.execute(
        "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
        "VALUES (%s,%s,%s,%s,%s,'CANCELLED')",
        (pnr4, raj_sched1, ndls, hwh, seat_ac1_1),
    )
    cur.execute("UPDATE Booking SET RefundAmount=%s WHERE PNRID=%s", (1620.00, pnr4))
    cnx.commit()

    vb_sched = schedule_id[(train_id["Vande Bharat Express"], (today + timedelta(days=1)).isoformat())]
    exec_chair = coach_by_type[(train_id["Vande Bharat Express"], "Executive Chair")]
    seat_exec1 = seat_lookup[(exec_chair, 1)]
    cstm = route_lookup[(train_id["Vande Bharat Express"], station_id["CSTM"])]
    pune = route_lookup[(train_id["Vande Bharat Express"], station_id["PUNE"])]
    pnr5 = insert_booking(("Siddharth", "Rao"), 950.00, "CONFIRMED", today)
    cur.execute(
        "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
        "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
        (pnr5, vb_sched, cstm, pune, seat_exec1),
    )
    cnx.commit()

    payments = [
        (pnr1, 1500.00, today, "UPI"),
        (pnr2, 1800.00, today, "NetBanking"),
        (pnr3, 3200.00, today, "Credit Card"),
        (pnr4, 1800.00, today - timedelta(days=1), "Debit Card"),
        (pnr5, 950.00, today, "UPI"),
    ]
    cur.executemany(
        "INSERT INTO Payment (PNRID, Amount, PaymentDate, Method) VALUES (%s,%s,%s,%s)",
        payments,
    )
    cnx.commit()
    cur.close()
    print("Sample data inserted.")


def main():
    cnx = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD)
    run_schema(cnx)
    cnx.database = DB_NAME
    seed_data(cnx)
    cnx.close()
    print("Done. Database 'RailwayReservationDB' is ready.")


if __name__ == "__main__":
    main()
