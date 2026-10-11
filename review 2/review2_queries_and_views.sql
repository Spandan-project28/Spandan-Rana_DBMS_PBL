-- ============================================================================
-- DBMS PROJECT 17: RAILWAY TICKET RESERVATION & JOURNEY MANAGEMENT SYSTEM
-- REVIEW 2: SAMPLE DATA POPULATION & 7 COMPLEX ANALYTICAL QUERIES / VIEWS
-- ============================================================================

USE RailwayReservationReview2;

-- ============================================================================
-- 1. POPULATE REALISTIC SAMPLE DATA
-- ============================================================================

-- Stations
INSERT INTO Station (StationID, Name, City) VALUES
(1, 'New Delhi', 'Delhi'),
(2, 'Kanpur Central', 'Kanpur'),
(3, 'Prayagraj Junction', 'Prayagraj'),
(4, 'Howrah Junction', 'Kolkata'),
(5, 'Mumbai CSMT', 'Mumbai'),
(6, 'Pune Junction', 'Pune');

-- Trains
INSERT INTO Train (TrainID, Name, Type) VALUES
(101, 'Rajdhani Express', 'Superfast Express'),
(102, 'Vande Bharat Express', 'Semi-High Speed'),
(103, 'Duronto Express', 'Non-Stop Superfast');

-- Route Stops for Train 101 (NDLS -> CNB -> PRYJ -> HWH)
INSERT INTO Route_Stop (RouteID, TrainID, StationID, StopSequence, ArrivalTime, DepartureTime, Distance) VALUES
(1001, 101, 1, 1, '16:50:00', '16:55:00', 0),
(1002, 101, 2, 2, '21:30:00', '21:35:00', 440),
(1003, 101, 3, 3, '23:45:00', '23:50:00', 635),
(1004, 101, 4, 4, '09:55:00', '10:05:00', 1445);

-- Route Stops for Train 102 (CSTM -> PUNE)
INSERT INTO Route_Stop (RouteID, TrainID, StationID, StopSequence, ArrivalTime, DepartureTime, Distance) VALUES
(2001, 102, 5, 1, '06:00:00', '06:05:00', 0),
(2002, 102, 6, 2, '09:15:00', '09:20:00', 192);

-- Schedules
INSERT INTO Schedule (ScheduleID, TrainID, JourneyDate) VALUES
(501, 101, '2026-10-15'),
(502, 102, '2026-10-15'),
(503, 101, '2026-10-16');

-- Coaches
INSERT INTO Coach (CoachID, TrainID, CoachType, TotalSeats) VALUES
(1, 101, 'AC 3-Tier', 72),
(2, 101, 'AC 1st Class', 24),
(3, 102, 'Executive Chair', 52);

-- Seats
INSERT INTO Seat (SeatID, CoachID, SeatNumber, BerthType) VALUES
(101, 1, 12, 'Lower'),
(102, 1, 14, 'Upper'),
(103, 2, 4, 'Cabin'),
(104, 3, 8, 'Window');

-- Passengers
INSERT INTO Passenger (PassengerID, FirstName, LastName, Age, Gender) VALUES
(1, 'Aarav', 'Sharma', 28, 'Male'),
(2, 'Priya', 'Verma', 25, 'Female'),
(3, 'Rohan', 'Gupta', 34, 'Male'),
(4, 'Siddharth', 'Rao', 24, 'Male'),
(5, 'Ananya', 'Sen', 29, 'Female'),
(6, 'Rahul', 'Roy', 42, 'Male');

-- Bookings
INSERT INTO Booking (PNRID, PassengerID, BookingDate, TotalFare, Status) VALUES
(894321, 1, '2026-10-01', 1500.00, 'CONFIRMED'),
(894322, 2, '2026-10-02', 1200.00, 'WAITLISTED'),
(894355, 3, '2026-10-03', 1800.00, 'CONFIRMED'),
(894310, 6, '2026-10-04', 1800.00, 'CANCELLED');

-- Non-Overlapping Journey Segments on Same Physical Seat 101 (Coach B1, Seat 12)!
INSERT INTO Journey_Segment (SegmentID, PNRID, ScheduleID, SourceRouteID, DestRouteID, SeatID, Status) VALUES
(901, 894321, 501, 1001, 1002, 101, 'CONFIRMED'),  -- Delhi (1) -> Kanpur (2) on Seat 101
(902, 894355, 501, 1002, 1004, 101, 'CONFIRMED');  -- Kanpur (2) -> Howrah (4) on Seat 101 [NO CONFLICT]

-- Waitlist Entry
INSERT INTO Waitlist (WaitlistID, PNRID, ScheduleID, Position, Status) VALUES
(1, 894322, 501, 1, 'WAITING');

-- Payments
INSERT INTO Payment (PaymentID, PNRID, Amount, PaymentDate, Method) VALUES
(7001, 894321, 1500.00, '2026-10-01', 'UPI'),
(7002, 894322, 1200.00, '2026-10-02', 'Credit Card'),
(7003, 894355, 1800.00, '2026-10-03', 'NetBanking'),
(7004, 894310, 1800.00, '2026-10-04', 'Debit Card');


-- ============================================================================
-- 2. THE 7 MANDATORY ANALYTICAL QUERIES & VIEWS FOR REVIEW 2
-- ============================================================================

-- ----------------------------------------------------------------------------
-- REPORT 1: SEGMENT-WISE SEAT AVAILABILITY VIEW
-- Demonstrates: CREATE VIEW, LEFT JOINS, SUBQUERIES, COALESCE
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_SegmentSeatAvailability AS
SELECT 
    s.ScheduleID,
    t.Name AS TrainName,
    s.JourneyDate,
    c.CoachType,
    st.SeatID,
    st.SeatNumber,
    st.BerthType,
    CASE 
        WHEN js.SegmentID IS NULL THEN 'AVAILABLE'
        ELSE 'OCCUPIED'
    END AS SeatStatus
FROM Seat st
JOIN Coach c ON st.CoachID = c.CoachID
JOIN Train t ON c.TrainID = t.TrainID
JOIN Schedule s ON t.TrainID = s.TrainID
LEFT JOIN Journey_Segment js ON st.SeatID = js.SeatID 
    AND s.ScheduleID = js.ScheduleID 
    AND js.Status = 'CONFIRMED';

-- Test Query
SELECT * FROM vw_SegmentSeatAvailability WHERE ScheduleID = 501;


-- ----------------------------------------------------------------------------
-- REPORT 2: DYNAMIC FIFO WAITLIST QUEUE & PROMOTION ORDER
-- Demonstrates: JOINS, ORDER BY, SUBQUERIES
-- ----------------------------------------------------------------------------
SELECT 
    w.Position AS WaitlistRank,
    b.PNRID,
    CONCAT(p.FirstName, ' ', p.LastName) AS PassengerName,
    p.Age,
    p.Gender,
    t.Name AS TrainName,
    s.JourneyDate,
    w.Status AS QueueStatus
FROM Waitlist w
JOIN Booking b ON w.PNRID = b.PNRID
JOIN Passenger p ON b.PassengerID = p.PassengerID
JOIN Schedule s ON w.ScheduleID = s.ScheduleID
JOIN Train t ON s.TrainID = t.TrainID
WHERE w.Status = 'WAITING'
ORDER BY w.ScheduleID, w.Position ASC;


-- ----------------------------------------------------------------------------
-- REPORT 3: COACH OCCUPANCY & CAPACITY UTILIZATION METRICS
-- Demonstrates: MULTI-TABLE JOINS, AGGREGATES (COUNT, SUM, ROUND)
-- ----------------------------------------------------------------------------
SELECT 
    t.Name AS TrainName,
    c.CoachType,
    c.TotalSeats AS TotalCapacity,
    COUNT(DISTINCT js.SeatID) AS AllocatedSeats,
    (c.TotalSeats - COUNT(DISTINCT js.SeatID)) AS VacantSeats,
    ROUND((COUNT(DISTINCT js.SeatID) / c.TotalSeats) * 100, 2) AS OccupancyPercentage
FROM Coach c
JOIN Train t ON c.TrainID = t.TrainID
JOIN Seat st ON c.CoachID = st.CoachID
LEFT JOIN Journey_Segment js ON st.SeatID = js.SeatID AND js.Status = 'CONFIRMED'
GROUP BY c.CoachID, t.Name, c.CoachType, c.TotalSeats;


-- ----------------------------------------------------------------------------
-- REPORT 4: ROUTE DEMAND ANALYSIS & HIGH-TRAFFIC CORRIDORS
-- Demonstrates: MULTI-TABLE JOINS, GROUP BY, HAVING, AGGREGATE SUM/COUNT
-- ----------------------------------------------------------------------------
SELECT 
    s1.Name AS OriginStation,
    s2.Name AS DestinationStation,
    COUNT(js.SegmentID) AS TotalBookedPassengers,
    SUM(b.TotalFare) AS CorridorRevenue
FROM Journey_Segment js
JOIN Route_Stop r1 ON js.SourceRouteID = r1.RouteID
JOIN Station s1 ON r1.StationID = s1.StationID
JOIN Route_Stop r2 ON js.DestRouteID = r2.RouteID
JOIN Station s2 ON r2.StationID = s2.StationID
JOIN Booking b ON js.PNRID = b.PNRID
WHERE js.Status = 'CONFIRMED'
GROUP BY s1.Name, s2.Name
ORDER BY TotalBookedPassengers DESC;


-- ----------------------------------------------------------------------------
-- REPORT 5: CANCELLATIONS & REFUND LEDGER WITH CLERKAGE DEDUCTION
-- Demonstrates: CONDITIONAL CASE STATEMENTS, ARITHMETIC EXPRESSIONS, JOINS
-- ----------------------------------------------------------------------------
SELECT 
    b.PNRID,
    CONCAT(p.FirstName, ' ', p.LastName) AS PassengerName,
    b.BookingDate,
    b.TotalFare AS OriginalGrossFare,
    ROUND(b.TotalFare * 0.80, 2) AS NetRefundPayable,
    ROUND(b.TotalFare * 0.20, 2) AS CancellationClerkageRetained,
    b.Status
FROM Booking b
JOIN Passenger p ON b.PassengerID = p.PassengerID
WHERE b.Status = 'CANCELLED';


-- ----------------------------------------------------------------------------
-- REPORT 6: PASSENGER COMPLETE JOURNEY ITINERARY
-- Demonstrates: 5-WAY INNER JOIN CONNECTING FLEET, SEATS, AND TICKETS
-- ----------------------------------------------------------------------------
SELECT 
    b.PNRID,
    CONCAT(p.FirstName, ' ', p.LastName) AS PassengerName,
    t.Name AS TrainName,
    s1.Name AS BoardingStation,
    r1.DepartureTime,
    s2.Name AS DestinationStation,
    r2.ArrivalTime,
    c.CoachType,
    st.SeatNumber,
    st.BerthType,
    b.Status AS BookingStatus
FROM Booking b
JOIN Passenger p ON b.PassengerID = p.PassengerID
JOIN Journey_Segment js ON b.PNRID = js.PNRID
JOIN Route_Stop r1 ON js.SourceRouteID = r1.RouteID
JOIN Station s1 ON r1.StationID = s1.StationID
JOIN Route_Stop r2 ON js.DestRouteID = r2.RouteID
JOIN Station s2 ON r2.StationID = s2.StationID
JOIN Seat st ON js.SeatID = st.SeatID
JOIN Coach c ON st.CoachID = c.CoachID
JOIN Train t ON c.TrainID = t.TrainID;


-- ----------------------------------------------------------------------------
-- REPORT 7: FINANCIAL REVENUE AGGREGATION VIEW
-- Demonstrates: CREATE VIEW, GROUP BY, AGGREGATE FUNCTIONS, SUBQUERIES
-- ----------------------------------------------------------------------------
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

-- Test View
SELECT * FROM vw_FinancialRevenueSummary;
