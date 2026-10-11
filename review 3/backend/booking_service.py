"""All database-facing business logic for the Railway Reservation app.

Every function here either takes an open (cnx, cur) pair or opens its own via
db.get_cursor(). Multi-step operations (booking, cancellation, promotion) run
inside a single transaction so the database is never left half-updated.
"""
from datetime import datetime, date

import mysql.connector

import db
from db import AppError

CLASS_MULTIPLIER = {
    "AC 1st Class": 6.5,
    "AC 2-Tier": 4.5,
    "AC 3-Tier": 3.5,
    "Sleeper": 1.2,
    "Executive Chair": 5.5,
}
QUOTA_MULTIPLIER = {"GN": 1.0, "SR": 0.8, "LD": 1.0, "TQ": 1.3}
VALID_GENDERS = {"Male", "Female", "Other"}
VALID_PAYMENT_METHODS = {"UPI", "Credit Card", "Debit Card", "NetBanking"}


# ---------------------------------------------------------------------------
# Fare engine (single source of truth — used by search, booking, preview and
# the fare calculator so results are always consistent)
# ---------------------------------------------------------------------------
def compute_fare(distance_km, coach_type, age=30, quota="GN"):
    base = 100
    dist_charge = round(distance_km * 0.6)
    class_mult = CLASS_MULTIPLIER.get(coach_type, 1.0)
    with_class = round((base + dist_charge) * class_mult)

    quota_mult = QUOTA_MULTIPLIER.get(quota, 1.0)
    sr_applies = age >= 60 or quota == "SR"
    sr_factor = 0.8 if sr_applies else 1.0
    with_quota = round(with_class * quota_mult * sr_factor)

    tatkal_surcharge = round(with_class * 0.3) if quota == "TQ" else 0
    sr_discount = round(with_class * 0.2) if sr_applies else 0
    gst = round(with_quota * 0.05)
    total = with_quota + gst

    return {
        "distanceKm": distance_km,
        "base": base,
        "distCharge": dist_charge,
        "classMult": class_mult,
        "tatkalSurcharge": tatkal_surcharge if quota == "TQ" else None,
        "seniorDiscount": sr_discount if sr_applies else None,
        "gst": gst,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Reference data (bootstrap) — cached client-side once, doesn't change often
# ---------------------------------------------------------------------------
def get_bootstrap():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT StationID id, Code code, Name name, City city, Zone zone FROM Station ORDER BY StationID")
        stations = cur.fetchall()
        cur.execute("SELECT TrainID id, Name name, Type type FROM Train ORDER BY TrainID")
        trains = cur.fetchall()
        cur.execute(
            "SELECT RouteID routeId, TrainID trainId, StationID stationId, StopSequence seq, "
            "ArrivalTime arr, DepartureTime dep, Distance dist FROM Route_Stop ORDER BY TrainID, StopSequence"
        )
        route_stops = cur.fetchall()
        for r in route_stops:
            r["arr"] = _time_str(r["arr"])
            r["dep"] = _time_str(r["dep"])
        cur.execute("SELECT CoachID id, TrainID trainId, CoachType type, TotalSeats totalSeats FROM Coach ORDER BY CoachID")
        coaches = cur.fetchall()
        cur.execute("SELECT ScheduleID id, TrainID trainId, JourneyDate date FROM Schedule ORDER BY ScheduleID")
        schedules = cur.fetchall()
        for s in schedules:
            s["date"] = s["date"].isoformat()
        return {
            "stations": stations,
            "trains": trains,
            "routeStops": route_stops,
            "coaches": coaches,
            "schedules": schedules,
        }


def _time_str(val):
    if val is None:
        return None
    total_seconds = int(val.total_seconds())
    h, rem = divmod(total_seconds, 3600)
    m, _s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def get_dashboard():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT COUNT(*) n FROM Booking")
        bookings = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Booking WHERE Status='CONFIRMED'")
        confirmed = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Booking WHERE Status='WAITLISTED'")
        waitlisted = cur.fetchone()["n"]
        cur.execute("SELECT COALESCE(SUM(TotalFare),0) rev FROM Booking WHERE Status != 'CANCELLED'")
        revenue = float(cur.fetchone()["rev"])

        cur.execute(
            "SELECT b.PNRID pnr, b.TotalFare fare, b.Status status, "
            "p.FirstName fname, p.LastName lname "
            "FROM Booking b JOIN Passenger p ON b.PassengerID=p.PassengerID "
            "ORDER BY b.PNRID DESC LIMIT 5"
        )
        recent_raw = cur.fetchall()
        recent = []
        for r in recent_raw:
            train = _train_for_pnr(cur, r["pnr"])
            recent.append({
                "pnr": r["pnr"], "fare": float(r["fare"]), "status": r["status"],
                "passenger": {"fname": r["fname"], "lname": r["lname"]},
                "train": train,
            })

        cur.execute(
            "SELECT t.TrainID trainId, t.Name name, "
            "COALESCE((SELECT SUM(c.TotalSeats) FROM Coach c WHERE c.TrainID=t.TrainID),0) totalSeats, "
            "COALESCE((SELECT COUNT(*) FROM Journey_Segment js "
            "   JOIN Seat st ON js.SeatID=st.SeatID JOIN Coach c2 ON st.CoachID=c2.CoachID "
            "   WHERE c2.TrainID=t.TrainID AND js.Status='CONFIRMED'),0) confirmedSeats "
            "FROM Train t ORDER BY t.TrainID"
        )
        occupancy = cur.fetchall()
        for r in occupancy:
            r["totalSeats"] = int(r["totalSeats"])
            r["confirmedSeats"] = int(r["confirmedSeats"])

        cur.execute("SELECT COUNT(*) n FROM Train")
        n_trains = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Station")
        n_stations = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Passenger")
        n_passengers = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Schedule")
        n_schedules = cur.fetchone()["n"]

        return {
            "kpis": {"bookings": bookings, "confirmed": confirmed, "waitlisted": waitlisted, "revenue": revenue},
            "recent": recent,
            "occupancy": occupancy,
            "quickstats": {"trains": n_trains, "stations": n_stations, "passengers": n_passengers, "schedules": n_schedules},
        }


def get_counts():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT COUNT(*) n FROM Booking")
        bookings = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Waitlist WHERE Status='WAITING'")
        waiting = cur.fetchone()["n"]
        return {"bookings": bookings, "waitlistWaiting": waiting}


def _train_for_pnr(cur, pnr):
    cur.execute(
        "SELECT t.TrainID id, t.Name name FROM Journey_Segment js "
        "JOIN Schedule s ON js.ScheduleID=s.ScheduleID JOIN Train t ON s.TrainID=t.TrainID "
        "WHERE js.PNRID=%s LIMIT 1", (pnr,)
    )
    row = cur.fetchone()
    if row:
        return row
    cur.execute(
        "SELECT t.TrainID id, t.Name name FROM Waitlist w "
        "JOIN Schedule s ON w.ScheduleID=s.ScheduleID JOIN Train t ON s.TrainID=t.TrainID "
        "WHERE w.PNRID=%s LIMIT 1", (pnr,)
    )
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def search_trains(from_id, to_id, journey_date, coach_class):
    if from_id == to_id:
        raise AppError("Origin and destination cannot be the same", 400)

    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT r1.TrainID trainId, t.Name name, t.Type type, "
            "r1.StopSequence srcSeq, r1.DepartureTime srcDep, r1.Distance srcDist, "
            "r2.StopSequence destSeq, r2.ArrivalTime destArr, r2.Distance destDist, "
            "r1.RouteID srcRouteId, r2.RouteID destRouteId, "
            "s1.Code srcCode, s1.Name srcName, s2.Code destCode, s2.Name destName "
            "FROM Route_Stop r1 "
            "JOIN Route_Stop r2 ON r1.TrainID = r2.TrainID AND r1.StopSequence < r2.StopSequence "
            "JOIN Train t ON r1.TrainID = t.TrainID "
            "JOIN Station s1 ON r1.StationID = s1.StationID "
            "JOIN Station s2 ON r2.StationID = s2.StationID "
            "WHERE r1.StationID = %s AND r2.StationID = %s",
            (from_id, to_id),
        )
        legs = cur.fetchall()

        cur.execute("SELECT ScheduleID, TrainID FROM Schedule WHERE JourneyDate = %s", (journey_date,))
        schedule_for_train = {row["TrainID"]: row["ScheduleID"] for row in cur.fetchall()}

        results = []
        for leg in legs:
            train_id = leg["trainId"]
            dist_km = leg["destDist"] - leg["srcDist"]
            dep_mins = _mins(leg["srcDep"])
            arr_mins = _mins(leg["destArr"])
            duration = arr_mins - dep_mins
            if duration < 0:
                duration += 24 * 60

            cur.execute(
                "SELECT CoachID id, CoachType type, TotalSeats totalSeats FROM Coach WHERE TrainID=%s"
                + ("" if coach_class in (None, "", "ALL") else " AND CoachType=%s"),
                (train_id,) if coach_class in (None, "", "ALL") else (train_id, coach_class),
            )
            coaches = cur.fetchall()

            schedule_id = schedule_for_train.get(train_id)
            coach_out = []
            for c in coaches:
                if schedule_id:
                    available = _available_seat_count(cur, schedule_id, c["id"], leg["srcRouteId"], leg["destRouteId"])
                else:
                    available = c["totalSeats"]
                fare = compute_fare(dist_km, c["type"])["total"]
                coach_out.append({
                    "coachId": c["id"], "type": c["type"], "totalSeats": c["totalSeats"],
                    "available": available, "fare": fare,
                })

            results.append({
                "trainId": train_id, "name": leg["name"], "type": leg["type"],
                "distanceKm": dist_km, "durationMins": duration,
                "srcCode": leg["srcCode"], "srcName": leg["srcName"], "srcDep": _time_str(leg["srcDep"]),
                "destCode": leg["destCode"], "destName": leg["destName"], "destArr": _time_str(leg["destArr"]),
                "coaches": coach_out,
            })

        return results


def _mins(td):
    if td is None:
        return 0
    return int(td.total_seconds() // 60)


# ---------------------------------------------------------------------------
# Seat allocation (the segment-overlap-aware core of the whole system)
# ---------------------------------------------------------------------------
_OVERLAP_EXISTS_SQL = """
    SELECT 1 FROM Journey_Segment js
    JOIN Route_Stop r_src ON js.SourceRouteID = r_src.RouteID
    JOIN Route_Stop r_dest ON js.DestRouteID = r_dest.RouteID
    JOIN Route_Stop req_src ON req_src.RouteID = %(src)s
    JOIN Route_Stop req_dest ON req_dest.RouteID = %(dest)s
    WHERE js.SeatID = st.SeatID
      AND js.ScheduleID = %(sched)s
      AND js.Status = 'CONFIRMED'
      AND NOT (req_dest.StopSequence <= r_src.StopSequence OR req_src.StopSequence >= r_dest.StopSequence)
"""


def _find_available_seat(cur, schedule_id, coach_id, src_route_id, dest_route_id):
    cur.execute(
        f"SELECT st.SeatID id, st.SeatNumber num FROM Seat st WHERE st.CoachID=%(coach)s "
        f"AND NOT EXISTS ({_OVERLAP_EXISTS_SQL}) ORDER BY st.SeatNumber LIMIT 1",
        {"coach": coach_id, "sched": schedule_id, "src": src_route_id, "dest": dest_route_id},
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _available_seat_count(cur, schedule_id, coach_id, src_route_id, dest_route_id):
    cur.execute(
        f"SELECT COUNT(*) n FROM Seat st WHERE st.CoachID=%(coach)s "
        f"AND NOT EXISTS ({_OVERLAP_EXISTS_SQL})",
        {"coach": coach_id, "sched": schedule_id, "src": src_route_id, "dest": dest_route_id},
    )
    return cur.fetchone()["n"]


def get_availability(train_id, coach_id, src_id, dest_id, journey_date):
    with db.get_cursor() as (cnx, cur):
        route = _resolve_route(cur, train_id, src_id, dest_id)
        cur.execute("SELECT TotalSeats total FROM Coach WHERE CoachID=%s AND TrainID=%s", (coach_id, train_id))
        coach = cur.fetchone()
        if not coach:
            raise AppError("Coach not found for this train", 404)

        schedule_id = _find_or_none_schedule(cur, train_id, journey_date)
        if schedule_id:
            available = _available_seat_count(cur, schedule_id, coach_id, route["srcRouteId"], route["destRouteId"])
        else:
            available = coach["total"]
        confirmed = coach["total"] - available
        pct = round(confirmed / coach["total"] * 100) if coach["total"] else 0
        return {
            "distanceKm": route["distKm"], "totalSeats": coach["total"],
            "confirmed": confirmed, "available": available, "occupancyPct": pct,
        }


def _resolve_route(cur, train_id, src_id, dest_id):
    cur.execute(
        "SELECT RouteID routeId, StopSequence seq, Distance dist FROM Route_Stop WHERE TrainID=%s AND StationID=%s",
        (train_id, src_id),
    )
    src = cur.fetchone()
    cur.execute(
        "SELECT RouteID routeId, StopSequence seq, Distance dist FROM Route_Stop WHERE TrainID=%s AND StationID=%s",
        (train_id, dest_id),
    )
    dest = cur.fetchone()
    if not src or not dest:
        raise AppError("Selected stations are not on this train's route", 400)
    if src["seq"] >= dest["seq"]:
        raise AppError("Destination must come after origin on this route", 400)
    return {"srcRouteId": src["routeId"], "destRouteId": dest["routeId"], "distKm": dest["dist"] - src["dist"]}


def _find_or_none_schedule(cur, train_id, journey_date):
    cur.execute("SELECT ScheduleID id FROM Schedule WHERE TrainID=%s AND JourneyDate=%s", (train_id, journey_date))
    row = cur.fetchone()
    return row["id"] if row else None


def _find_or_create_schedule(cur, train_id, journey_date):
    sid = _find_or_none_schedule(cur, train_id, journey_date)
    if sid:
        return sid
    cur.execute("INSERT INTO Schedule (TrainID, JourneyDate) VALUES (%s,%s)", (train_id, journey_date))
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Fare endpoint (fare calculator page)
# ---------------------------------------------------------------------------
def get_fare_quote(train_id, src_id, dest_id, coach_type, age, quota):
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT RouteID, StopSequence seq, Distance dist FROM Route_Stop WHERE TrainID=%s AND StationID=%s",
            (train_id, src_id),
        )
        src = cur.fetchone()
        cur.execute(
            "SELECT RouteID, StopSequence seq, Distance dist FROM Route_Stop WHERE TrainID=%s AND StationID=%s",
            (train_id, dest_id),
        )
        dest = cur.fetchone()
        if not src or not dest or src["seq"] >= dest["seq"]:
            raise AppError("Invalid direction for this train", 400)
        dist_km = dest["dist"] - src["dist"]
        return compute_fare(dist_km, coach_type, age, quota)


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------
def book_ticket(payload):
    fname = (payload.get("fname") or "").strip()
    lname = (payload.get("lname") or "").strip()
    age = payload.get("age")
    gender = payload.get("gender")
    journey_date = payload.get("date")
    train_id = payload.get("trainId")
    coach_id = payload.get("coachId")
    src_id = payload.get("srcId")
    dest_id = payload.get("destId")
    payment = payload.get("payment")

    if not fname or not lname:
        raise AppError("Enter passenger name", 400)
    if not isinstance(age, int) or age < 1 or age > 125:
        raise AppError("Age must be between 1 and 125", 400)
    if gender not in VALID_GENDERS:
        raise AppError("Invalid gender", 400)
    if not train_id or not coach_id:
        raise AppError("Choose a train and coach", 400)
    if not src_id or not dest_id:
        raise AppError("Choose origin and destination", 400)
    if src_id == dest_id:
        raise AppError("Origin and destination cannot be the same", 400)
    if payment not in VALID_PAYMENT_METHODS:
        raise AppError("Invalid payment method", 400)
    if not journey_date:
        raise AppError("Choose a journey date", 400)

    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT TrainID id, Name name FROM Train WHERE TrainID=%s", (train_id,))
        train = cur.fetchone()
        if not train:
            raise AppError("Train not found", 404)
        cur.execute("SELECT CoachID id, CoachType type, TotalSeats total FROM Coach WHERE CoachID=%s AND TrainID=%s", (coach_id, train_id))
        coach = cur.fetchone()
        if not coach:
            raise AppError("Coach not found for this train", 404)

        route = _resolve_route(cur, train_id, src_id, dest_id)
        fare = compute_fare(route["distKm"], coach["type"])["total"]

        schedule_id = _find_or_create_schedule(cur, train_id, journey_date)

        cur.execute(
            "INSERT INTO Passenger (FirstName, LastName, Age, Gender) VALUES (%s,%s,%s,%s)",
            (fname, lname, age, gender),
        )
        passenger_id = cur.lastrowid

        seat_id = _find_available_seat(cur, schedule_id, coach_id, route["srcRouteId"], route["destRouteId"])
        status = "CONFIRMED" if seat_id else "WAITLISTED"

        cur.execute(
            "INSERT INTO Booking (PassengerID, BookingDate, TotalFare, Status) VALUES (%s, CURDATE(), %s, %s)",
            (passenger_id, fare, status),
        )
        pnr = cur.lastrowid

        waitlist_position = None
        if status == "CONFIRMED":
            try:
                cur.execute(
                    "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
                    "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
                    (pnr, schedule_id, route["srcRouteId"], route["destRouteId"], seat_id),
                )
            except mysql.connector.errors.DatabaseError as e:
                # Trigger caught a race (another request took the seat first) — fall back to waitlist.
                status = "WAITLISTED"
        if status == "WAITLISTED":
            cur.execute(
                "SELECT COUNT(*) n FROM Waitlist WHERE ScheduleID=%s AND Status='WAITING'", (schedule_id,)
            )
            waitlist_position = cur.fetchone()["n"] + 1
            cur.execute(
                "INSERT INTO Waitlist (PNRID, ScheduleID, RequestedCoachID, SourceRouteID, DestRouteID, Position, Status) "
                "VALUES (%s,%s,%s,%s,%s,%s,'WAITING')",
                (pnr, schedule_id, coach_id, route["srcRouteId"], route["destRouteId"], waitlist_position),
            )

        cur.execute(
            "INSERT INTO Payment (PNRID, Amount, PaymentDate, Method) VALUES (%s,%s,CURDATE(),%s)",
            (pnr, fare, payment),
        )

        cur.execute("SELECT Code code, Name name FROM Station WHERE StationID=%s", (src_id,))
        src_station = cur.fetchone()
        cur.execute("SELECT Code code, Name name FROM Station WHERE StationID=%s", (dest_id,))
        dest_station = cur.fetchone()
        sched_date_str = journey_date if isinstance(journey_date, str) else journey_date.isoformat()

        return {
            "pnr": pnr, "passId": passenger_id, "status": status, "fare": fare,
            "waitlistPosition": waitlist_position,
            "passenger": {"fname": fname, "lname": lname, "age": age, "gender": gender},
            "date": date.today().isoformat(), "schedDate": sched_date_str,
            "trainId": train_id, "trainName": train["name"], "schedId": schedule_id,
            "coachType": coach["type"],
            "srcCode": src_station["code"], "srcName": src_station["name"], "srcStation": src_id,
            "destCode": dest_station["code"], "destName": dest_station["name"], "destStation": dest_id,
            "payment": payment,
        }


# ---------------------------------------------------------------------------
# Bookings listing / detail
# ---------------------------------------------------------------------------
def list_bookings(status=None):
    with db.get_cursor() as (cnx, cur):
        sql = (
            "SELECT b.PNRID pnr, b.PassengerID passId, p.FirstName fname, p.LastName lname, "
            "p.Age age, p.Gender gender, b.BookingDate date, b.TotalFare fare, b.Status status, b.RefundAmount refundAmount "
            "FROM Booking b JOIN Passenger p ON b.PassengerID = p.PassengerID "
        )
        params = ()
        if status:
            sql += "WHERE b.Status=%s "
            params = (status,)
        sql += "ORDER BY b.PNRID DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()

        out = []
        for r in rows:
            journey = _journey_for_pnr(cur, r["pnr"])
            method = _latest_payment_method(cur, r["pnr"])
            out.append({
                "pnr": r["pnr"], "passId": r["passId"],
                "passenger": {"fname": r["fname"], "lname": r["lname"], "age": r["age"], "gender": r["gender"]},
                "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else r["date"],
                "fare": float(r["fare"]), "status": r["status"], "payment": method,
                "refundAmount": float(r["refundAmount"]) if r["refundAmount"] is not None else None,
                **journey,
            })
        return out


def get_booking(pnr):
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT b.PNRID pnr, b.PassengerID passId, p.FirstName fname, p.LastName lname, "
            "p.Age age, p.Gender gender, b.BookingDate date, b.TotalFare fare, b.Status status, b.RefundAmount refundAmount "
            "FROM Booking b JOIN Passenger p ON b.PassengerID = p.PassengerID WHERE b.PNRID=%s", (pnr,)
        )
        r = cur.fetchone()
        if not r:
            raise AppError("PNR not found", 404)
        journey = _journey_for_pnr(cur, pnr)
        method = _latest_payment_method(cur, pnr)
        return {
            "pnr": r["pnr"], "passId": r["passId"],
            "passenger": {"fname": r["fname"], "lname": r["lname"], "age": r["age"], "gender": r["gender"]},
            "date": r["date"].isoformat() if hasattr(r["date"], "isoformat") else r["date"],
            "fare": float(r["fare"]), "status": r["status"], "payment": method,
            "refundAmount": float(r["refundAmount"]) if r["refundAmount"] is not None else None,
            **journey,
        }


def _journey_for_pnr(cur, pnr):
    cur.execute(
        "SELECT t.TrainID trainId, t.Name trainName, s.ScheduleID schedId, s.JourneyDate schedDate, c.CoachType coachType, "
        "s1.Code srcCode, s1.Name srcName, s1.StationID srcStation, "
        "s2.Code destCode, s2.Name destName, s2.StationID destStation "
        "FROM Journey_Segment js "
        "JOIN Schedule s ON js.ScheduleID = s.ScheduleID JOIN Train t ON s.TrainID = t.TrainID "
        "JOIN Route_Stop r1 ON js.SourceRouteID = r1.RouteID JOIN Station s1 ON r1.StationID = s1.StationID "
        "JOIN Route_Stop r2 ON js.DestRouteID = r2.RouteID JOIN Station s2 ON r2.StationID = s2.StationID "
        "JOIN Seat st ON js.SeatID = st.SeatID JOIN Coach c ON st.CoachID = c.CoachID "
        "WHERE js.PNRID=%s ORDER BY js.SegmentID DESC LIMIT 1",
        (pnr,),
    )
    row = cur.fetchone()
    if row:
        row["schedDate"] = row["schedDate"].isoformat()
        return row
    cur.execute(
        "SELECT t.TrainID trainId, t.Name trainName, s.ScheduleID schedId, s.JourneyDate schedDate, c.CoachType coachType, "
        "s1.Code srcCode, s1.Name srcName, s1.StationID srcStation, "
        "s2.Code destCode, s2.Name destName, s2.StationID destStation "
        "FROM Waitlist w "
        "JOIN Schedule s ON w.ScheduleID = s.ScheduleID JOIN Train t ON s.TrainID = t.TrainID "
        "JOIN Coach c ON w.RequestedCoachID = c.CoachID "
        "JOIN Route_Stop r1 ON w.SourceRouteID = r1.RouteID JOIN Station s1 ON r1.StationID = s1.StationID "
        "JOIN Route_Stop r2 ON w.DestRouteID = r2.RouteID JOIN Station s2 ON r2.StationID = s2.StationID "
        "WHERE w.PNRID=%s ORDER BY w.WaitlistID DESC LIMIT 1",
        (pnr,),
    )
    row = cur.fetchone()
    if row:
        row["schedDate"] = row["schedDate"].isoformat()
        return row
    return {
        "trainId": None, "trainName": None, "schedId": None, "schedDate": None, "coachType": None,
        "srcCode": None, "srcName": None, "srcStation": None,
        "destCode": None, "destName": None, "destStation": None,
    }


def _latest_payment_method(cur, pnr):
    cur.execute("SELECT Method FROM Payment WHERE PNRID=%s ORDER BY PaymentID DESC LIMIT 1", (pnr,))
    row = cur.fetchone()
    return row["Method"] if row else None


# ---------------------------------------------------------------------------
# Cancellation (+ auto-promotion)
# ---------------------------------------------------------------------------
def preview_cancel(pnr):
    booking = get_booking(pnr)
    if booking["status"] == "CANCELLED":
        return {**booking, "refund": 0}
    refund = _estimate_refund(booking)
    return {**booking, "refund": refund}


def _estimate_refund(booking):
    if booking["status"] == "WAITLISTED":
        return round(booking["fare"], 2)
    dep_dt = _departure_datetime(booking)
    return _tiered_refund(booking["fare"], dep_dt)


def _departure_datetime(booking):
    if not booking.get("schedDate"):
        return None
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT rs.DepartureTime dep FROM Journey_Segment js "
            "JOIN Route_Stop rs ON js.SourceRouteID = rs.RouteID WHERE js.PNRID=%s ORDER BY js.SegmentID DESC LIMIT 1",
            (booking["pnr"],),
        )
        row = cur.fetchone()
    sched_date = date.fromisoformat(booking["schedDate"])
    if not row or row["dep"] is None:
        return datetime.combine(sched_date, datetime.min.time())
    return datetime.combine(sched_date, datetime.min.time()) + row["dep"]


def _tiered_refund(fare, dep_dt):
    if dep_dt is None:
        hours = 999
    else:
        hours = (dep_dt - datetime.now()).total_seconds() / 3600
    if hours > 48:
        pct = 0.90
    elif hours >= 24:
        pct = 0.75
    else:
        pct = 0.50
    return round(fare * pct, 2)


def cancel_booking(pnr):
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT Status, TotalFare FROM Booking WHERE PNRID=%s FOR UPDATE", (pnr,))
        booking = cur.fetchone()
        if not booking:
            raise AppError("PNR not found", 404)
        if booking["Status"] == "CANCELLED":
            raise AppError("Ticket already cancelled", 409)

        was_waitlisted = booking["Status"] == "WAITLISTED"
        fare = float(booking["TotalFare"])
        schedule_id = None
        dep_dt = None

        if was_waitlisted:
            cur.execute("SELECT ScheduleID FROM Waitlist WHERE PNRID=%s AND Status='WAITING'", (pnr,))
            wl = cur.fetchone()
            if wl:
                schedule_id = wl["ScheduleID"]
                cur.execute("UPDATE Waitlist SET Status='CANCELLED', Position=NULL WHERE PNRID=%s AND Status='WAITING'", (pnr,))
            refund = round(fare, 2)
        else:
            cur.execute(
                "SELECT js.SegmentID segId, js.ScheduleID schedId, s.JourneyDate journeyDate, rs.DepartureTime dep "
                "FROM Journey_Segment js JOIN Schedule s ON js.ScheduleID=s.ScheduleID "
                "JOIN Route_Stop rs ON js.SourceRouteID = rs.RouteID "
                "WHERE js.PNRID=%s AND js.Status='CONFIRMED'", (pnr,)
            )
            seg = cur.fetchone()
            if seg:
                schedule_id = seg["schedId"]
                dep_dt = datetime.combine(seg["journeyDate"], datetime.min.time())
                if seg["dep"] is not None:
                    dep_dt = dep_dt + seg["dep"]
                cur.execute("UPDATE Journey_Segment SET Status='CANCELLED' WHERE SegmentID=%s", (seg["segId"],))
            refund = _tiered_refund(fare, dep_dt)

        cur.execute("UPDATE Booking SET Status='CANCELLED', RefundAmount=%s WHERE PNRID=%s", (refund, pnr))

        promoted_pnr = None
        if schedule_id and not was_waitlisted:
            promoted_pnr = _try_promote_next(cur, schedule_id)
        if schedule_id:
            _renumber_waitlist(cur, schedule_id)

        return {"pnr": pnr, "refund": refund, "promotedPnr": promoted_pnr}


def _try_promote_next(cur, schedule_id):
    cur.execute(
        "SELECT WaitlistID id, PNRID pnr, RequestedCoachID coachId, SourceRouteID src, DestRouteID dest "
        "FROM Waitlist WHERE ScheduleID=%s AND Status='WAITING' ORDER BY Position ASC", (schedule_id,)
    )
    for wl in cur.fetchall():
        seat_id = _find_available_seat(cur, schedule_id, wl["coachId"], wl["src"], wl["dest"])
        if seat_id:
            cur.execute(
                "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
                "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
                (wl["pnr"], schedule_id, wl["src"], wl["dest"], seat_id),
            )
            cur.execute("UPDATE Booking SET Status='CONFIRMED' WHERE PNRID=%s", (wl["pnr"],))
            cur.execute("UPDATE Waitlist SET Status='PROMOTED', Position=NULL WHERE WaitlistID=%s", (wl["id"],))
            return wl["pnr"]
    return None


def _renumber_waitlist(cur, schedule_id):
    cur.execute(
        "SELECT WaitlistID id FROM Waitlist WHERE ScheduleID=%s AND Status='WAITING' ORDER BY Position ASC",
        (schedule_id,),
    )
    for i, row in enumerate(cur.fetchall(), start=1):
        cur.execute("UPDATE Waitlist SET Position=%s WHERE WaitlistID=%s", (i, row["id"]))


# ---------------------------------------------------------------------------
# Waitlist management
# ---------------------------------------------------------------------------
def list_waitlist():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT w.WaitlistID id, w.Position position, w.PNRID pnr, w.ScheduleID schedId, "
            "b.TotalFare fare, p.FirstName fname, p.LastName lname, "
            "t.Name trainName, c.CoachType coachType, "
            "s1.Code srcCode, s2.Code destCode "
            "FROM Waitlist w "
            "JOIN Booking b ON w.PNRID = b.PNRID JOIN Passenger p ON b.PassengerID = p.PassengerID "
            "JOIN Schedule sc ON w.ScheduleID = sc.ScheduleID JOIN Train t ON sc.TrainID = t.TrainID "
            "JOIN Coach c ON w.RequestedCoachID = c.CoachID "
            "JOIN Route_Stop r1 ON w.SourceRouteID = r1.RouteID JOIN Station s1 ON r1.StationID = s1.StationID "
            "JOIN Route_Stop r2 ON w.DestRouteID = r2.RouteID JOIN Station s2 ON r2.StationID = s2.StationID "
            "WHERE w.Status='WAITING' ORDER BY w.ScheduleID, w.Position"
        )
        active = cur.fetchall()
        for r in active:
            r["fare"] = float(r["fare"])
        cur.execute("SELECT COUNT(*) n FROM Waitlist")
        total = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Waitlist WHERE Status='PROMOTED'")
        promoted = cur.fetchone()["n"]
        return {"active": active, "totalEverQueued": total, "promotedCount": promoted}


def promote_one(waitlist_id):
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT WaitlistID id, PNRID pnr, ScheduleID schedId, RequestedCoachID coachId, "
            "SourceRouteID src, DestRouteID dest, Status status "
            "FROM Waitlist WHERE WaitlistID=%s FOR UPDATE", (waitlist_id,)
        )
        wl = cur.fetchone()
        if not wl:
            raise AppError("Waitlist entry not found", 404)
        if wl["status"] != "WAITING":
            raise AppError("This entry is no longer waiting", 409)

        seat_id = _find_available_seat(cur, wl["schedId"], wl["coachId"], wl["src"], wl["dest"])
        if not seat_id:
            raise AppError("No seat is free yet for this passenger's requested class/route", 409)

        cur.execute(
            "INSERT INTO Journey_Segment (PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) "
            "VALUES (%s,%s,%s,%s,%s,'CONFIRMED')",
            (wl["pnr"], wl["schedId"], wl["src"], wl["dest"], seat_id),
        )
        cur.execute("UPDATE Booking SET Status='CONFIRMED' WHERE PNRID=%s", (wl["pnr"],))
        cur.execute("UPDATE Waitlist SET Status='PROMOTED', Position=NULL WHERE WaitlistID=%s", (waitlist_id,))
        _renumber_waitlist(cur, wl["schedId"])
        return {"pnr": wl["pnr"]}


def promote_all():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT DISTINCT ScheduleID FROM Waitlist WHERE Status='WAITING'")
        schedules = [r["ScheduleID"] for r in cur.fetchall()]
        promoted = []
        for sid in schedules:
            while True:
                pnr = _try_promote_next(cur, sid)
                if not pnr:
                    break
                promoted.append(pnr)
            _renumber_waitlist(cur, sid)
        return {"promoted": promoted}


def cancel_waitlist_entry(waitlist_id):
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT PNRID pnr, ScheduleID schedId, Status status FROM Waitlist WHERE WaitlistID=%s FOR UPDATE", (waitlist_id,))
        wl = cur.fetchone()
        if not wl:
            raise AppError("Waitlist entry not found", 404)
        if wl["status"] != "WAITING":
            raise AppError("This entry is no longer waiting", 409)
        cur.execute("UPDATE Waitlist SET Status='CANCELLED', Position=NULL WHERE WaitlistID=%s", (waitlist_id,))
        cur.execute("UPDATE Booking SET Status='CANCELLED' WHERE PNRID=%s", (wl["pnr"],))
        _renumber_waitlist(cur, wl["schedId"])
        return {"pnr": wl["pnr"]}


# ---------------------------------------------------------------------------
# CRUD manager
# ---------------------------------------------------------------------------
def list_trains():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT t.TrainID id, t.Name name, t.Type type, "
            "COALESCE((SELECT COUNT(*) FROM Coach c WHERE c.TrainID=t.TrainID),0) coachCount, "
            "COALESCE((SELECT SUM(c.TotalSeats) FROM Coach c WHERE c.TrainID=t.TrainID),0) totalSeats "
            "FROM Train t ORDER BY t.TrainID"
        )
        rows = cur.fetchall()
        for r in rows:
            r["totalSeats"] = int(r["totalSeats"])
        return rows


def create_train(name, type_):
    name = (name or "").strip()
    if not name:
        raise AppError("Train name is required", 400)
    with db.get_cursor() as (cnx, cur):
        cur.execute("INSERT INTO Train (Name, Type) VALUES (%s,%s)", (name, type_ or "Express"))
        return {"id": cur.lastrowid, "name": name, "type": type_ or "Express"}


def update_train(train_id, name, type_):
    name = (name or "").strip()
    if not name:
        raise AppError("Train name is required", 400)
    with db.get_cursor() as (cnx, cur):
        cur.execute("UPDATE Train SET Name=%s, Type=%s WHERE TrainID=%s", (name, type_, train_id))
        if cur.rowcount == 0:
            raise AppError("Train not found", 404)
        return {"id": train_id, "name": name, "type": type_}


def delete_train(train_id):
    _guarded_delete(
        "SELECT COUNT(*) n FROM Coach WHERE TrainID=%s UNION ALL SELECT COUNT(*) FROM Schedule WHERE TrainID=%s UNION ALL SELECT COUNT(*) FROM Route_Stop WHERE TrainID=%s",
        (train_id, train_id, train_id),
        "DELETE FROM Train WHERE TrainID=%s", (train_id,),
        "Cannot delete: this train has coaches, schedules or route stops defined",
        "Train not found",
    )


def list_stations():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT StationID id, Code code, Name name, City city, Zone zone FROM Station ORDER BY StationID")
        return cur.fetchall()


def create_station(code, name, city, zone):
    code = (code or "").strip().upper()
    name = (name or "").strip()
    if not code or not name:
        raise AppError("Station code and name are required", 400)
    with db.get_cursor() as (cnx, cur):
        try:
            cur.execute(
                "INSERT INTO Station (Code, Name, City, Zone) VALUES (%s,%s,%s,%s)",
                (code, name, city or "", zone or ""),
            )
        except mysql.connector.errors.IntegrityError:
            raise AppError(f"Station code '{code}' already exists", 409)
        return {"id": cur.lastrowid, "code": code, "name": name, "city": city, "zone": zone}


def delete_station(station_id):
    _guarded_delete(
        "SELECT COUNT(*) n FROM Route_Stop WHERE StationID=%s",
        (station_id,),
        "DELETE FROM Station WHERE StationID=%s", (station_id,),
        "Cannot delete: this station is used on one or more train routes",
        "Station not found",
    )


def list_passengers():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT p.PassengerID id, p.FirstName fname, p.LastName lname, p.Age age, p.Gender gender, "
            "(SELECT COUNT(*) FROM Booking b WHERE b.PassengerID=p.PassengerID) bookingCount "
            "FROM Passenger p ORDER BY p.PassengerID"
        )
        return cur.fetchall()


def create_passenger(fname, lname, age, gender):
    fname = (fname or "").strip()
    lname = (lname or "").strip()
    if not fname or not lname:
        raise AppError("First and last name are required", 400)
    if not isinstance(age, int) or age < 1 or age > 125:
        raise AppError("Age must be between 1 and 125", 400)
    if gender not in VALID_GENDERS:
        raise AppError("Invalid gender", 400)
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "INSERT INTO Passenger (FirstName, LastName, Age, Gender) VALUES (%s,%s,%s,%s)",
            (fname, lname, age, gender),
        )
        return {"id": cur.lastrowid, "fname": fname, "lname": lname, "age": age, "gender": gender}


def delete_passenger(passenger_id):
    _guarded_delete(
        "SELECT COUNT(*) n FROM Booking WHERE PassengerID=%s",
        (passenger_id,),
        "DELETE FROM Passenger WHERE PassengerID=%s", (passenger_id,),
        "Cannot delete: this passenger has booking records",
        "Passenger not found",
    )


def list_schedules():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT s.ScheduleID id, s.TrainID trainId, t.Name trainName, s.JourneyDate date, "
            "(SELECT COUNT(*) FROM Journey_Segment js WHERE js.ScheduleID=s.ScheduleID) bookingCount "
            "FROM Schedule s JOIN Train t ON s.TrainID=t.TrainID ORDER BY s.ScheduleID"
        )
        rows = cur.fetchall()
        for r in rows:
            r["date"] = r["date"].isoformat()
        return rows


def create_schedule(train_id, journey_date):
    if not train_id or not journey_date:
        raise AppError("Train and journey date are required", 400)
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT TrainID FROM Train WHERE TrainID=%s", (train_id,))
        if not cur.fetchone():
            raise AppError("Train not found", 404)
        try:
            cur.execute("INSERT INTO Schedule (TrainID, JourneyDate) VALUES (%s,%s)", (train_id, journey_date))
        except mysql.connector.errors.IntegrityError:
            raise AppError("A schedule for this train on this date already exists", 409)
        return {"id": cur.lastrowid, "trainId": train_id, "date": journey_date}


def _guarded_delete(check_sql, check_params, delete_sql, delete_params, block_message, not_found_message):
    with db.get_cursor() as (cnx, cur):
        cur.execute(check_sql, check_params)
        rows = cur.fetchall()
        if any((r.get("n") if isinstance(r, dict) else r[0]) for r in rows):
            raise AppError(block_message, 409)
        cur.execute(delete_sql, delete_params)
        if cur.rowcount == 0:
            raise AppError(not_found_message, 404)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def report_occupancy():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT t.TrainID trainId, t.Name trainName, "
            "COALESCE((SELECT SUM(c.TotalSeats) FROM Coach c WHERE c.TrainID=t.TrainID),0) totalSeats, "
            "COALESCE((SELECT COUNT(*) FROM Journey_Segment js JOIN Seat st ON js.SeatID=st.SeatID "
            "  JOIN Coach c2 ON st.CoachID=c2.CoachID WHERE c2.TrainID=t.TrainID AND js.Status='CONFIRMED'),0) confirmed, "
            "COALESCE((SELECT COUNT(*) FROM Waitlist w JOIN Coach c3 ON w.RequestedCoachID=c3.CoachID "
            "  WHERE c3.TrainID=t.TrainID AND w.Status='WAITING'),0) waitlisted "
            "FROM Train t ORDER BY t.TrainID"
        )
        rows = cur.fetchall()
        for r in rows:
            r["totalSeats"] = int(r["totalSeats"])
            r["occupancyPct"] = round(r["confirmed"] / r["totalSeats"] * 100, 1) if r["totalSeats"] else 0.0
        return rows


def report_revenue():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT t.TrainID trainId, t.Name trainName, "
            "COUNT(DISTINCT js.PNRID) bookings, "
            "COALESCE(SUM(b.TotalFare),0) revenue "
            "FROM Train t "
            "LEFT JOIN Schedule s ON s.TrainID=t.TrainID "
            "LEFT JOIN Journey_Segment js ON js.ScheduleID=s.ScheduleID AND js.Status='CONFIRMED' "
            "LEFT JOIN Booking b ON js.PNRID=b.PNRID AND b.Status != 'CANCELLED' "
            "GROUP BY t.TrainID, t.Name ORDER BY t.TrainID"
        )
        rows = cur.fetchall()
        for r in rows:
            r["revenue"] = float(r["revenue"])
        return rows


def report_segments():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT js.SegmentID segId, js.PNRID pnr, CONCAT(p.FirstName,' ',p.LastName) passenger, "
            "s1.Code srcCode, r1.StopSequence srcSeq, s2.Code destCode, r2.StopSequence destSeq, "
            "st.SeatNumber seatNumber, js.Status status "
            "FROM Journey_Segment js "
            "JOIN Booking b ON js.PNRID=b.PNRID JOIN Passenger p ON b.PassengerID=p.PassengerID "
            "JOIN Route_Stop r1 ON js.SourceRouteID=r1.RouteID JOIN Station s1 ON r1.StationID=s1.StationID "
            "JOIN Route_Stop r2 ON js.DestRouteID=r2.RouteID JOIN Station s2 ON r2.StationID=s2.StationID "
            "JOIN Seat st ON js.SeatID=st.SeatID "
            "ORDER BY js.SegmentID DESC"
        )
        return cur.fetchall()


def report_passengers():
    with db.get_cursor() as (cnx, cur):
        cur.execute(
            "SELECT p.PassengerID id, CONCAT(p.FirstName,' ',p.LastName) name, p.Age age, p.Gender gender, "
            "COUNT(b.PNRID) bookings, "
            "COALESCE(SUM(CASE WHEN b.Status != 'CANCELLED' THEN b.TotalFare ELSE 0 END),0) spent "
            "FROM Passenger p LEFT JOIN Booking b ON p.PassengerID=b.PassengerID "
            "GROUP BY p.PassengerID, p.FirstName, p.LastName, p.Age, p.Gender ORDER BY p.PassengerID"
        )
        rows = cur.fetchall()
        for r in rows:
            r["spent"] = float(r["spent"])
        return rows


def report_summary():
    with db.get_cursor() as (cnx, cur):
        cur.execute("SELECT COUNT(*) n FROM Booking")
        total = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Booking WHERE Status='CONFIRMED'")
        confirmed = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Booking WHERE Status='WAITLISTED'")
        waitlisted = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Booking WHERE Status='CANCELLED'")
        cancelled = cur.fetchone()["n"]
        cur.execute("SELECT COALESCE(SUM(TotalFare),0) rev FROM Booking WHERE Status != 'CANCELLED'")
        revenue = float(cur.fetchone()["rev"])
        cur.execute("SELECT COUNT(*) n FROM Waitlist")
        wl_total = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) n FROM Waitlist WHERE Status='PROMOTED'")
        wl_promoted = cur.fetchone()["n"]

        return {
            "totalRevenue": revenue,
            "confirmRate": round(confirmed / total * 100) if total else 0,
            "wlClearRate": round(wl_promoted / wl_total * 100) if wl_total else 0,
            "cancelRate": round(cancelled / total * 100) if total else 0,
            "statusDist": {"confirmed": confirmed, "waitlisted": waitlisted, "cancelled": cancelled, "total": total},
        }
