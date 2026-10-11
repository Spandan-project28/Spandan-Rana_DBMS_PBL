# Concise Data Dictionary — Review 2

## Project: Railway Ticket Reservation & Journey Management System (Project 17)

This data dictionary defines the structure, data types, nullability, primary/foreign key relationships, and integrity constraints for all 11 relational tables normalized up to Third Normal Form (3NF).

---

### 1. `Station` Table
*Description:* Master catalog of railway stations in the network.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `StationID` | `INT` | **PK** | NOT NULL | Unique numeric station identifier. |
| `Name` | `VARCHAR(100)` | - | NOT NULL | Station name (e.g., 'New Delhi', 'Kanpur Central'). |
| `City` | `VARCHAR(100)` | - | NOT NULL | City location. |

---

### 2. `Train` Table
*Description:* Master fleet catalog of operational train locomotives.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `TrainID` | `INT` | **PK** | NOT NULL | Unique train identifier. |
| `Name` | `VARCHAR(100)` | - | NOT NULL | Train commercial title (e.g., 'Rajdhani Express'). |
| `Type` | `VARCHAR(50)` | - | NULL | Classification (`DEFAULT 'Express'`). |

---

### 3. `Route_Stop` Table
*Description:* Associative junction defining the ordered stations along a train's journey.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `RouteID` | `INT` | **PK** | NOT NULL | Unique route stop ID. |
| `TrainID` | `INT` | **FK** | NOT NULL | References `Train(TrainID)`. |
| `StationID` | `INT` | **FK** | NOT NULL | References `Station(StationID)`. |
| `StopSequence` | `INT` | - | NOT NULL | `CHECK (StopSequence > 0)`. Unique `(TrainID, StopSequence)`. |
| `ArrivalTime` | `TIME` | - | NULL | Scheduled train arrival time. |
| `DepartureTime`| `TIME` | - | NULL | Scheduled train departure (`CHECK (DepartureTime >= ArrivalTime)`). |
| `Distance` | `INT` | - | NULL | `CHECK (Distance >= 0)` cumulative KM from source. |

---

### 4. `Schedule` Table
*Description:* Represents specific operational trip dates for trains.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `ScheduleID` | `INT` | **PK** | NOT NULL | Unique schedule journey ID. |
| `TrainID` | `INT` | **FK** | NOT NULL | References `Train(TrainID)`. |
| `JourneyDate` | `DATE` | - | NOT NULL | Date of journey departure. |

---

### 5. `Coach` Table
*Description:* Physical coach cars attached to a train.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `CoachID` | `INT` | **PK** | NOT NULL | Unique coach identifier. |
| `TrainID` | `INT` | **FK** | NOT NULL | References `Train(TrainID)`. |
| `CoachType` | `VARCHAR(50)` | - | NOT NULL | Class (AC 1st Class, AC 2-Tier, AC 3-Tier, Sleeper). |
| `TotalSeats` | `INT` | - | NOT NULL | `CHECK (TotalSeats > 0)` physical seat capacity. |

---

### 6. `Seat` Table
*Description:* Individual physical seats/berths within a coach.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `SeatID` | `INT` | **PK** | NOT NULL | Unique seat identifier. |
| `CoachID` | `INT` | **FK** | NOT NULL | References `Coach(CoachID)`. |
| `SeatNumber` | `INT` | - | NOT NULL | `CHECK (SeatNumber > 0)`. Unique `(CoachID, SeatNumber)`. |
| `BerthType` | `VARCHAR(50)` | - | NOT NULL | Lower, Middle, Upper, Side Lower, Side Upper, Window. |

---

### 7. `Passenger` Table
*Description:* Registered travelers booking tickets.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `PassengerID` | `INT` | **PK** | NOT NULL | Unique passenger identifier. |
| `FirstName` | `VARCHAR(50)` | - | NOT NULL | Given name. |
| `LastName` | `VARCHAR(50)` | - | NOT NULL | Surname. |
| `Age` | `INT` | - | NOT NULL | `CHECK (Age > 0 AND Age <= 125)`. |
| `Gender` | `VARCHAR(10)` | - | NOT NULL | `CHECK (Gender IN ('Male', 'Female', 'Other'))`. |

---

### 8. `Booking` Table
*Description:* Master PNR reservation transaction records.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `PNRID` | `INT` | **PK** | NOT NULL | Unique 6-digit Passenger Name Record number. |
| `PassengerID` | `INT` | **FK** | NOT NULL | References `Passenger(PassengerID)`. |
| `BookingDate` | `DATE` | - | NOT NULL | Date when reservation was made. |
| `TotalFare` | `DECIMAL(10,2)`| - | NOT NULL | `CHECK (TotalFare >= 0.00)` non-negative fare. |
| `Status` | `VARCHAR(20)` | - | NOT NULL | `CHECK (Status IN ('CONFIRMED', 'WAITLISTED', 'CANCELLED'))`. |

---

### 9. `Journey_Segment` Table
*Description:* Granular station-to-station hop reservation on a specific physical seat.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `SegmentID` | `INT` | **PK** | NOT NULL | Unique journey segment ID. |
| `PNRID` | `INT` | **FK** | NOT NULL | References `Booking(PNRID)`. |
| `ScheduleID` | `INT` | **FK** | NOT NULL | References `Schedule(ScheduleID)`. |
| `SourceRouteID`| `INT` | **FK** | NOT NULL | References `Route_Stop(RouteID)` origin hop. |
| `DestRouteID` | `INT` | **FK** | NOT NULL | References `Route_Stop(RouteID)` destination hop. |
| `SeatID` | `INT` | **FK** | NOT NULL | References `Seat(SeatID)`. |
| `Status` | `VARCHAR(20)` | - | NOT NULL | `DEFAULT 'CONFIRMED'` (`CHECK IN ('CONFIRMED', 'CANCELLED')`). |

---

### 10. `Waitlist` Table
*Description:* Sequential FIFO queue for overbooked passenger requests.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `WaitlistID` | `INT` | **PK** | NOT NULL | Unique waitlist record ID. |
| `PNRID` | `INT` | **FK** | NOT NULL | References `Booking(PNRID)`. |
| `ScheduleID` | `INT` | **FK** | NOT NULL | References `Schedule(ScheduleID)`. |
| `Position` | `INT` | **UNIQUE** | NOT NULL | `CHECK (Position > 0)`. Unique `(ScheduleID, Position)`. |
| `Status` | `VARCHAR(20)` | - | NOT NULL | `DEFAULT 'WAITING'` (`CHECK IN ('WAITING', 'PROMOTED', 'CANCELLED')`). |

---

### 11. `Payment` Table
*Description:* Financial settlement log for tickets.

| Attribute Name | Data Type | Key Type | Nullable | Constraints & Description |
| :--- | :--- | :--- | :--- | :--- |
| `PaymentID` | `INT` | **PK** | NOT NULL | Unique transaction ID. |
| `PNRID` | `INT` | **FK** | NOT NULL | References `Booking(PNRID)`. |
| `Amount` | `DECIMAL(10,2)`| - | NOT NULL | `CHECK (Amount >= 0.00)`. |
| `PaymentDate` | `DATE` | - | NOT NULL | Settlement date. |
| `Method` | `VARCHAR(50)` | - | NOT NULL | `CHECK (Method IN ('UPI', 'Credit Card', 'Debit Card', 'NetBanking'))`. |
