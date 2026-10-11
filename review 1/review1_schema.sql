CREATE DATABASE IF NOT EXISTS RailwayReservation;
USE RailwayReservation;

CREATE TABLE Station (
    StationID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    City VARCHAR(100)
);

CREATE TABLE Train (
    TrainID INT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Type VARCHAR(50)
);

CREATE TABLE Route_Stop (
    RouteID INT PRIMARY KEY,
    TrainID INT,
    StationID INT,
    StopSequence INT,
    ArrivalTime TIME,
    DepartureTime TIME,
    Distance INT,
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID),
    FOREIGN KEY (StationID) REFERENCES Station(StationID)
);

CREATE TABLE Schedule (
    ScheduleID INT PRIMARY KEY,
    TrainID INT,
    JourneyDate DATE,
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID)
);

CREATE TABLE Coach (
    CoachID INT PRIMARY KEY,
    TrainID INT,
    CoachType VARCHAR(50),
    TotalSeats INT,
    FOREIGN KEY (TrainID) REFERENCES Train(TrainID)
);

CREATE TABLE Seat (
    SeatID INT PRIMARY KEY,
    CoachID INT,
    SeatNumber INT,
    BerthType VARCHAR(50),
    FOREIGN KEY (CoachID) REFERENCES Coach(CoachID)
);

CREATE TABLE Passenger (
    PassengerID INT PRIMARY KEY,
    FirstName VARCHAR(50),
    LastName VARCHAR(50),
    Age INT,
    Gender VARCHAR(10)
);

CREATE TABLE Booking (
    PNRID INT PRIMARY KEY,
    PassengerID INT,
    BookingDate DATE,
    TotalFare DECIMAL(10,2),
    Status VARCHAR(20),
    FOREIGN KEY (PassengerID) REFERENCES Passenger(PassengerID)
);

CREATE TABLE Journey_Segment (
    SegmentID INT PRIMARY KEY,
    PNRID INT,
    ScheduleID INT,
    SourceRouteID INT,
    DestRouteID INT,
    SeatID INT,
    Status VARCHAR(20),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID),
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID),
    FOREIGN KEY (SourceRouteID) REFERENCES Route_Stop(RouteID),
    FOREIGN KEY (DestRouteID) REFERENCES Route_Stop(RouteID),
    FOREIGN KEY (SeatID) REFERENCES Seat(SeatID)
);

CREATE TABLE Waitlist (
    WaitlistID INT PRIMARY KEY,
    PNRID INT,
    ScheduleID INT,
    Position INT,
    Status VARCHAR(20),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID),
    FOREIGN KEY (ScheduleID) REFERENCES Schedule(ScheduleID)
);

CREATE TABLE Payment (
    PaymentID INT PRIMARY KEY,
    PNRID INT,
    Amount DECIMAL(10,2),
    PaymentDate DATE,
    Method VARCHAR(50),
    FOREIGN KEY (PNRID) REFERENCES Booking(PNRID)
);
