-- ============================================================================
-- CLOUD-HOSTED VARIANT OF schema.sql
--
-- Free managed MySQL (Clever Cloud) gives one fixed, already-created database
-- and does not allow DROP DATABASE / CREATE DATABASE / USE. This file is
-- identical to schema.sql except for that: it drops and recreates tables
-- inside whatever database the connection is already pointed at, instead of
-- dropping/creating the database itself. Keep this in sync with schema.sql
-- if the table structure changes there.
-- ============================================================================

DROP TABLE IF EXISTS Payment;
DROP TABLE IF EXISTS Waitlist;
DROP TABLE IF EXISTS Journey_Segment;
DROP TABLE IF EXISTS Booking;
DROP TABLE IF EXISTS Passenger;
DROP TABLE IF EXISTS Seat;
DROP TABLE IF EXISTS Coach;
DROP TABLE IF EXISTS Schedule;
DROP TABLE IF EXISTS Route_Stop;
DROP TABLE IF EXISTS Train;
DROP TABLE IF EXISTS Station;

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

-- 10. WAITLIST (FIFO queue; carries the requested segment — see schema.sql header note)
CREATE TABLE Waitlist (
    WaitlistID INT PRIMARY KEY AUTO_INCREMENT,
    PNRID INT NOT NULL,
    ScheduleID INT NOT NULL,
    RequestedCoachID INT NOT NULL,
    SourceRouteID INT NOT NULL,
    DestRouteID INT NOT NULL,
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
-- INDEXES
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
-- TRIGGER: PREVENT OVERLAPPING SEAT SEGMENTS
-- Omitted here: Clever Cloud's free "Dev" MySQL plan does not grant the
-- SUPER privilege needed to create triggers under binary logging. The app
-- never relies on this trigger at runtime anyway — booking_service.py's
-- _find_available_seat() already excludes overlapping segments before any
-- INSERT is issued (see schema.sql for the full trigger, used locally).
-- ============================================================================

-- ============================================================================
-- VIEWS
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
