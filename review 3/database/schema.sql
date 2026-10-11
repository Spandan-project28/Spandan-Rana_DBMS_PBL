-- ============================================================================
-- DBMS PROJECT 17: RAILWAY TICKET RESERVATION & JOURNEY MANAGEMENT SYSTEM
-- REVIEW 3: FINAL SCHEMA (structure only, no data — see seed.py for data)
--
-- Builds on the Review 2 schema (review 2/review2_schema_ddl.sql). Two
-- deliberate, documented refinements were made here to support a real,
-- working application rather than a static demo:
--
--   1. Station gains Code + Zone. The UI (built in Review 3's mock stage)
--      displays a station code (e.g. "NDLS") and railway zone everywhere.
--      Both attributes depend only on StationID, so this stays in 3NF.
--
--   2. Waitlist gains RequestedCoachID / SourceRouteID / DestRouteID.
--      The original schema only records WHERE a seat is booked via
--      Journey_Segment, which is only created once a seat is actually
--      assigned. A waitlisted booking has no seat yet, so without these
--      columns the system would forget which class/route the passenger
--      wanted the moment they were waitlisted, making promotion
--      impossible to do correctly. Each new attribute is a single FK
--      that depends only on WaitlistID, so 3NF is preserved.
--
--   3. Booking.PassengerID and most reference-data foreign keys were
--      changed from ON DELETE CASCADE to the default RESTRICT. Review 2's
--      cascades would silently wipe a passenger's booking/payment history
--      when the passenger record was deleted, and could cascade-delete a
--      train's live segments when the train row was removed. Blocking the
--      delete and surfacing a clear error is the correct behaviour for a
--      system that has to protect real transactional data.
-- ============================================================================

DROP DATABASE IF EXISTS RailwayReservationDB;
CREATE DATABASE RailwayReservationDB;
USE RailwayReservationDB;

-- 1. STATION
CREATE TABLE Station (
    StationID INT PRIMARY KEY AUTO_INCREMENT,
    Code VARCHAR(10) NOT NULL UNIQUE,
    Name VARCHAR(100) NOT NULL,
    City VARCHAR(100) NOT NULL,
    Zone VARCHAR(10) NOT NULL
);

-- 2. TRAIN
CREATE TABLE Train (
    TrainID INT PRIMARY KEY AUTO_INCREMENT,
    Name VARCHAR(100) NOT NULL,
    Type VARCHAR(50) NOT NULL DEFAULT 'Express'
);

-- 3. ROUTE_STOP (associative entity resolving Train <-> Station M:N)
CREATE TABLE Route_Stop (
    RouteID INT PRIMARY KEY AUTO_INCREMENT,
    TrainID INT NOT NULL,
    StationID INT NOT NULL,
    StopSequence INT NOT NULL CHECK (StopSequence > 0),
    ArrivalTime TIME NULL,
    DepartureTime TIME NULL,
    Distance INT NOT NULL DEFAULT 0 CHECK (Distance >= 0),
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE RESTRICT,
    FOREIGN KEY (StationID) REFERENCES Station(StationID) ON DELETE RESTRICT,
    UNIQUE (TrainID, StopSequence),
    CONSTRAINT chk_departure_after_arrival
        CHECK (DepartureTime IS NULL OR ArrivalTime IS NULL OR DepartureTime >= ArrivalTime)
);

-- 4. SCHEDULE (a specific train running on a specific calendar date)
CREATE TABLE Schedule (
    ScheduleID INT PRIMARY KEY AUTO_INCREMENT,
    TrainID INT NOT NULL,
    JourneyDate DATE NOT NULL,
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE RESTRICT,
    UNIQUE (TrainID, JourneyDate)
);

-- 5. COACH
CREATE TABLE Coach (
    CoachID INT PRIMARY KEY AUTO_INCREMENT,
    TrainID INT NOT NULL,
    CoachType VARCHAR(50) NOT NULL,
    TotalSeats INT NOT NULL CHECK (TotalSeats > 0),
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE RESTRICT
);

-- 6. SEAT
CREATE TABLE Seat (
    SeatID INT PRIMARY KEY AUTO_INCREMENT,
    CoachID INT NOT NULL,
    SeatNumber INT NOT NULL CHECK (SeatNumber > 0),
    BerthType VARCHAR(50) NOT NULL,
    FOREIGN KEY (CoachID) REFERENCES Coach(CoachID) ON DELETE RESTRICT,
    UNIQUE (CoachID, SeatNumber)
);

-- 7. PASSENGER
CREATE TABLE Passenger (
    PassengerID INT PRIMARY KEY AUTO_INCREMENT,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Age INT NOT NULL CHECK (Age > 0 AND Age <= 125),
    Gender VARCHAR(10) NOT NULL CHECK (Gender IN ('Male', 'Female', 'Other'))
);

-- 8. BOOKING (PNR header)
CREATE TABLE Booking (
    PNRID INT PRIMARY KEY AUTO_INCREMENT,
    PassengerID INT NOT NULL,
    BookingDate DATE NOT NULL,
    TotalFare DECIMAL(10,2) NOT NULL CHECK (TotalFare >= 0.00),
    Status VARCHAR(20) NOT NULL CHECK (Status IN ('CONFIRMED', 'WAITLISTED', 'CANCELLED')),
    -- Set only on cancellation, to the actual amount refunded under the
    -- time-to-departure policy in force at that moment. Kept so cancellation
    -- history/reports show what really happened, not a value re-guessed
    -- from today's clock.
    RefundAmount DECIMAL(10,2) NULL CHECK (RefundAmount IS NULL OR RefundAmount >= 0.00),
    FOREIGN KEY (PassengerID) REFERENCES Passenger(PassengerID) ON DELETE RESTRICT
);

-- 9. JOURNEY_SEGMENT (associative entity: PNR -> exact Seat for one hop)
CREATE TABLE Journey_Segment (
    SegmentID INT PRIMARY KEY AUTO_INCREMENT,
    PNRID INT NOT NULL,
    ScheduleID INT NOT NULL,
    SourceRouteID INT NOT NULL,
    DestRouteID INT NOT NULL,
    SeatID INT NOT NULL,
    Status VARCHAR(20) NOT NULL DEFAULT 'CONFIRMED' CHECK (Status IN ('CONFIRMED', 'CANCELLED')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE,
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID) ON DELETE RESTRICT,
    FOREIGN KEY (SourceRouteID) REFERENCES Route_Stop(RouteID) ON DELETE RESTRICT,
    FOREIGN KEY (DestRouteID) REFERENCES Route_Stop(RouteID) ON DELETE RESTRICT,
    FOREIGN KEY (SeatID) REFERENCES Seat(SeatID) ON DELETE RESTRICT
);

-- 10. WAITLIST (FIFO queue; carries the requested segment — see header note)
CREATE TABLE Waitlist (
    WaitlistID INT PRIMARY KEY AUTO_INCREMENT,
    PNRID INT NOT NULL,
    ScheduleID INT NOT NULL,
    RequestedCoachID INT NOT NULL,
    SourceRouteID INT NOT NULL,
    DestRouteID INT NOT NULL,
    -- NULL once a row leaves the queue (PROMOTED/CANCELLED); MySQL allows
    -- multiple NULLs in a UNIQUE index, so this lets remaining WAITING rows
    -- be safely renumbered without colliding with a row that no longer
    -- holds an active queue slot.
    Position INT NULL CHECK (Position IS NULL OR Position > 0),
    Status VARCHAR(20) NOT NULL DEFAULT 'WAITING' CHECK (Status IN ('WAITING', 'PROMOTED', 'CANCELLED')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE,
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID) ON DELETE RESTRICT,
    FOREIGN KEY (RequestedCoachID) REFERENCES Coach(CoachID) ON DELETE RESTRICT,
    FOREIGN KEY (SourceRouteID) REFERENCES Route_Stop(RouteID) ON DELETE RESTRICT,
    FOREIGN KEY (DestRouteID) REFERENCES Route_Stop(RouteID) ON DELETE RESTRICT,
    UNIQUE (ScheduleID, Position)
);

-- 11. PAYMENT
CREATE TABLE Payment (
    PaymentID INT PRIMARY KEY AUTO_INCREMENT,
    PNRID INT NOT NULL,
    Amount DECIMAL(10,2) NOT NULL CHECK (Amount >= 0.00),
    PaymentDate DATE NOT NULL,
    Method VARCHAR(50) NOT NULL CHECK (Method IN ('UPI', 'Credit Card', 'Debit Card', 'NetBanking')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE
);

-- ============================================================================
-- INDEXES ON FREQUENTLY SEARCHED / JOINED ATTRIBUTES
-- ============================================================================
CREATE INDEX idx_routestop_station        ON Route_Stop(StationID);
CREATE INDEX idx_schedule_train_date      ON Schedule(TrainID, JourneyDate);
CREATE INDEX idx_coach_train              ON Coach(TrainID);
CREATE INDEX idx_segment_seat_sched_status ON Journey_Segment(SeatID, ScheduleID, Status);
CREATE INDEX idx_segment_pnr              ON Journey_Segment(PNRID);
CREATE INDEX idx_booking_status           ON Booking(Status);
CREATE INDEX idx_booking_passenger        ON Booking(PassengerID);
CREATE INDEX idx_waitlist_schedule_status ON Waitlist(ScheduleID, Status, Position);
CREATE INDEX idx_passenger_name           ON Passenger(LastName, FirstName);

-- ============================================================================
-- TRIGGER: PREVENT OVERLAPPING SEAT SEGMENTS (carried over from Review 2)
-- This is the core business rule: the same physical seat may be reserved by
-- different passengers only for non-overlapping station-to-station hops.
-- ============================================================================
DELIMITER //

CREATE TRIGGER trg_prevent_seat_segment_overlap
BEFORE INSERT ON Journey_Segment
FOR EACH ROW
BEGIN
    DECLARE new_src_seq INT;
    DECLARE new_dest_seq INT;
    DECLARE overlap_count INT;

    SELECT StopSequence INTO new_src_seq FROM Route_Stop WHERE RouteID = NEW.SourceRouteID;
    SELECT StopSequence INTO new_dest_seq FROM Route_Stop WHERE RouteID = NEW.DestRouteID;

    IF new_src_seq >= new_dest_seq THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Integrity Violation: Destination StopSequence must be strictly greater than Source StopSequence.';
    END IF;

    SELECT COUNT(*) INTO overlap_count
    FROM Journey_Segment js
    JOIN Route_Stop r_src ON js.SourceRouteID = r_src.RouteID
    JOIN Route_Stop r_dest ON js.DestRouteID = r_dest.RouteID
    WHERE js.SeatID = NEW.SeatID
      AND js.ScheduleID = NEW.ScheduleID
      AND js.Status = 'CONFIRMED'
      AND NOT (new_dest_seq <= r_src.StopSequence OR new_src_seq >= r_dest.StopSequence);

    IF overlap_count > 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Concurrency Conflict: The requested seat is already reserved across overlapping journey segments.';
    END IF;
END //

DELIMITER ;

-- ============================================================================
-- VIEWS (Review 2 continuity + used by the Analytics & Reports page)
-- ============================================================================
CREATE OR REPLACE VIEW vw_SegmentSeatAvailability AS
SELECT
    s.ScheduleID,
    t.Name AS TrainName,
    s.JourneyDate,
    c.CoachType,
    st.SeatID,
    st.SeatNumber,
    st.BerthType,
    CASE WHEN js.SegmentID IS NULL THEN 'AVAILABLE' ELSE 'OCCUPIED' END AS SeatStatus
FROM Seat st
JOIN Coach c ON st.CoachID = c.CoachID
JOIN Train t ON c.TrainID = t.TrainID
JOIN Schedule s ON t.TrainID = s.TrainID
LEFT JOIN Journey_Segment js ON st.SeatID = js.SeatID
    AND s.ScheduleID = js.ScheduleID
    AND js.Status = 'CONFIRMED';

CREATE OR REPLACE VIEW vw_FinancialRevenueSummary AS
SELECT
    t.Type AS TrainCategory,
    COUNT(DISTINCT b.PNRID) AS ConfirmedBookingsCount,
    SUM(p.Amount) AS GrossCollectedRevenue,
    ROUND(AVG(p.Amount), 2) AS AverageTicketPrice
FROM Train t
JOIN Schedule s ON t.TrainID = s.TrainID
JOIN Journey_Segment js ON s.ScheduleID = js.ScheduleID
JOIN Booking b ON js.PNRID = b.PNRID
JOIN Payment p ON b.PNRID = p.PNRID
WHERE b.Status = 'CONFIRMED'
GROUP BY t.Type;
