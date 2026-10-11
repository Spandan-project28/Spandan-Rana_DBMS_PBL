-- ============================================================================
-- DBMS PROJECT 17: RAILWAY TICKET RESERVATION & JOURNEY MANAGEMENT SYSTEM
-- REVIEW 2: ADVANCED DDL SCHEMA WITH INTEGRITY CONSTRAINTS, CHECKS & TRIGGERS
-- Normalized up to Third Normal Form (3NF)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS RailwayReservationReview2;
USE RailwayReservationReview2;

-- 1. STATION TABLE
CREATE TABLE Station (
    StationID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    City VARCHAR(100) NOT NULL
);

-- 2. TRAIN TABLE
CREATE TABLE Train (
    TrainID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Type VARCHAR(50) DEFAULT 'Express'
);

-- 3. ROUTE_STOP TABLE (With StopSequence & Distance Check Constraints)
CREATE TABLE Route_Stop (
    RouteID INT PRIMARY KEY,
    TrainID INT NOT NULL,
    StationID INT NOT NULL,
    StopSequence INT NOT NULL CHECK (StopSequence > 0),
    ArrivalTime TIME,
    DepartureTime TIME,
    Distance INT DEFAULT 0 CHECK (Distance >= 0),
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE CASCADE,
    FOREIGN KEY (StationID) REFERENCES Station(StationID) ON DELETE CASCADE,
    UNIQUE (TrainID, StopSequence),
    CONSTRAINT chk_departure_after_arrival CHECK (DepartureTime IS NULL OR ArrivalTime IS NULL OR DepartureTime >= ArrivalTime)
);

-- 4. SCHEDULE TABLE
CREATE TABLE Schedule (
    ScheduleID INT PRIMARY KEY,
    TrainID INT NOT NULL,
    JourneyDate DATE NOT NULL,
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE CASCADE
);

-- 5. COACH TABLE (With TotalSeats Positive Check)
CREATE TABLE Coach (
    CoachID INT PRIMARY KEY,
    TrainID INT NOT NULL,
    CoachType VARCHAR(50) NOT NULL,
    TotalSeats INT NOT NULL CHECK (TotalSeats > 0),
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID) ON DELETE CASCADE
);

-- 6. SEAT TABLE (With SeatNumber Check)
CREATE TABLE Seat (
    SeatID INT PRIMARY KEY,
    CoachID INT NOT NULL,
    SeatNumber INT NOT NULL CHECK (SeatNumber > 0),
    BerthType VARCHAR(50) NOT NULL,
    FOREIGN KEY (CoachID) REFERENCES Coach(CoachID) ON DELETE CASCADE,
    UNIQUE (CoachID, SeatNumber)
);

-- 7. PASSENGER TABLE (With Age and Gender Integrity)
CREATE TABLE Passenger (
    PassengerID INT PRIMARY KEY,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50) NOT NULL,
    Age INT NOT NULL CHECK (Age > 0 AND Age <= 125),
    Gender VARCHAR(10) NOT NULL CHECK (Gender IN ('Male', 'Female', 'Other'))
);

-- 8. BOOKING TABLE (With Non-Negative Fare Check)
CREATE TABLE Booking (
    PNRID INT PRIMARY KEY,
    PassengerID INT NOT NULL,
    BookingDate DATE NOT NULL,
    TotalFare DECIMAL(10,2) NOT NULL CHECK (TotalFare >= 0.00),
    Status VARCHAR(20) NOT NULL CHECK (Status IN ('CONFIRMED', 'WAITLISTED', 'CANCELLED')),
    FOREIGN KEY (PassengerID) REFERENCES Passenger(PassengerID) ON DELETE CASCADE
);

-- 9. JOURNEY_SEGMENT TABLE (Multi-Hop Atomic Reservation)
CREATE TABLE Journey_Segment (
    SegmentID INT PRIMARY KEY,
    PNRID INT NOT NULL,
    ScheduleID INT NOT NULL,
    SourceRouteID INT NOT NULL,
    DestRouteID INT NOT NULL,
    SeatID INT NOT NULL,
    Status VARCHAR(20) DEFAULT 'CONFIRMED' CHECK (Status IN ('CONFIRMED', 'CANCELLED')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE,
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID) ON DELETE CASCADE,
    FOREIGN KEY (SourceRouteID) REFERENCES Route_Stop(RouteID),
    FOREIGN KEY (DestRouteID) REFERENCES Route_Stop(RouteID),
    FOREIGN KEY (SeatID) REFERENCES Seat(SeatID)
);

-- 10. WAITLIST TABLE (With Unique Position per Schedule)
CREATE TABLE Waitlist (
    WaitlistID INT PRIMARY KEY,
    PNRID INT NOT NULL,
    ScheduleID INT NOT NULL,
    Position INT NOT NULL CHECK (Position > 0),
    Status VARCHAR(20) DEFAULT 'WAITING' CHECK (Status IN ('WAITING', 'PROMOTED', 'CANCELLED')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE,
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID) ON DELETE CASCADE,
    UNIQUE (ScheduleID, Position)
);

-- 11. PAYMENT TABLE (With Non-Negative Amount Check)
CREATE TABLE Payment (
    PaymentID INT PRIMARY KEY,
    PNRID INT NOT NULL,
    Amount DECIMAL(10,2) NOT NULL CHECK (Amount >= 0.00),
    PaymentDate DATE NOT NULL,
    Method VARCHAR(50) NOT NULL CHECK (Method IN ('UPI', 'Credit Card', 'Debit Card', 'NetBanking')),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID) ON DELETE CASCADE
);

-- ============================================================================
-- ADVANCED DATABASE TRIGGER: PREVENT OVERLAPPING SEAT SEGMENTS
-- ============================================================================
DELIMITER //

CREATE TRIGGER trg_prevent_seat_segment_overlap
BEFORE INSERT ON Journey_Segment
FOR EACH ROW
BEGIN
    DECLARE new_src_seq INT;
    DECLARE new_dest_seq INT;
    DECLARE overlap_count INT;

    -- Fetch stop sequences for requested segment
    SELECT StopSequence INTO new_src_seq FROM Route_Stop WHERE RouteID = NEW.SourceRouteID;
    SELECT StopSequence INTO new_dest_seq FROM Route_Stop WHERE RouteID = NEW.DestRouteID;

    -- Validate that source sequence is strictly before destination sequence
    IF new_src_seq >= new_dest_seq THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Integrity Violation: Destination StopSequence must be strictly greater than Source StopSequence.';
    END IF;

    -- Check for overlapping confirmed reservations on the same Seat and Schedule
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
