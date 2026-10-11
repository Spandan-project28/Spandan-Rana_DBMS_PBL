# Railway Ticket Reservation & Journey Management System
### DBMS Project-Based Learning (PBL) — Project 17

A full-stack, transactional Relational Database Management System (RDBMS) for railway reservation and journey management. The system models multi-segment train journeys, segment-aware seat inventory, transaction-safe booking, waitlist maintenance with FIFO queuing, tiered cancellations, and real-time operational reporting.

---

## 📁 Repository Structure

```
.
├── Project Report/
│   └── RAILWAY TICKET RESERVATION-final draft.docx    # Comprehensive final report
├── review 1/
│   ├── presentation.html                             # Review 1 interactive slides
│   └── review1_schema.sql                            # Initial conceptual 3NF schema
├── review 2/
│   ├── data_dictionary.md                            # Comprehensive schema dictionary
│   ├── presentation.html                             # Review 2 interactive slides
│   ├── review2_schema_ddl.sql                        # Hardened DDL with constraints & trigger
│   └── review2_queries_and_views.sql                 # Analytical joins, aggregates & views
├── review 3/
│   ├── app.html                                      # Full frontend dashboard & reservation UI
│   ├── server.py                                     # Lightweight static server
│   ├── backend/
│   │   ├── app.py                                    # Flask REST API server
│   │   ├── booking_service.py                        # SQL business logic & transactional services
│   │   ├── db.py                                     # Connection pooling & error handling
│   │   ├── config.py                                 # Environment-based DB config
│   │   └── requirements.txt                          # Python dependencies
│   ├── database/
│   │   ├── schema.sql                                # Final MySQL 3NF schema & trigger
│   │   └── seed.py                                   # Automated database creation & seed data
│   └── tests/
│       ├── test_api.py                               # Comprehensive API integration test suite
│       └── requirements.txt                          # Test runner dependencies
└── Review3_Presentation_Script.txt                   # Complete presentation script for Review 3
```

---

## 🚀 Quick Start (Review 3 Application)

### 1. Prerequisites
- **Python 3.10+**
- **MySQL 8.0+** running locally on port 3306

### 2. Setup Virtual Environment & Dependencies
```powershell
cd "review 3"
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
```

### 3. Initialize & Seed Database
Set your MySQL root password and run the seed script:
```powershell
$env:RAILWAY_DB_PASSWORD = "your-mysql-password"
.\.venv\Scripts\python.exe database\seed.py
```

### 4. Start the Application
```powershell
cd backend
$env:RAILWAY_DB_PASSWORD = "your-mysql-password"
..\.venv\Scripts\python.exe app.py
```
Open **http://127.0.0.1:5000/** in your web browser.

---

## 🛠 Features & Database Highlights

- **Segment-Level Seat Allocation**: Solves interval-overlap booking across intermediate stations (`trg_prevent_seat_segment_overlap` trigger).
- **FIFO Waitlist Engine**: Automatic queue management and promotion when confirmed seats are cancelled.
- **Dynamic Fare Engine**: Calculates fare based on distance, coach class multiplier, concession quotas, and Tatkal surcharges.
- **Full CRUD Management**: Stations, trains, coaches, and passengers with referential integrity protection.
- **Live Reporting**: Occupancy analytics, revenue aggregation, and segment occupancy tracking.
