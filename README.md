# KindKitchen — Backend (FastAPI + PostgreSQL)

Backend API for KindKitchen, a food-donation platform connecting **Restaurants**, **NGOs**,
**Donors**, and **Delivery Agents**.

## Stack
- FastAPI, Uvicorn
- PostgreSQL (psycopg2)
- JWT auth (python-jose), bcrypt password hashing (passlib)
- Razorpay payment gateway (with automatic MOCK fallback)

## Quick start

### 1. Database (Docker)
```bash
docker run -d --name kk-postgres \
  -e POSTGRES_PASSWORD=12122005 -e POSTGRES_USER=postgres -e POSTGRES_DB=kathir \
  -p 5432:5432 postgres:16
```

### 2. Install + configure
```bash
pip install -r requirements.txt
cd "Fastapi backend"
cp .env.example .env        # edit values if needed
```

### 3. Run
```bash
# from inside "Fastapi backend"
uvicorn main:app --port 8000
```
Tables are auto-created on startup. Health check: http://localhost:8000/  → `{"message":"Server is running"}`
Interactive docs: http://localhost:8000/docs

## Key endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/users/signup` | create account (email + password) |
| POST | `/users/register` | add role + profile (Donor/Restaurant/NGO/Delivery_Agent) |
| POST | `/login` | returns JWT + role |
| POST | `/fooditems/add` | restaurant posts food |
| GET  | `/fooditems/firstpagefoodinfo` | browse food |
| POST | `/orders/createorder/{ngoid}` | NGO places order (Wallet/UPI/...) |
| GET  | `/orders/pending` | delivery agents see pickups |
| PUT  | `/orders/assign` | delivery agent claims an order |
| POST | `/payments/donor-to-ngo/{donor_id}` | record donation, credit NGO wallet |
| POST | `/payments/create-order` | create a gateway order (Razorpay/mock) |
| POST | `/payments/verify` | verify payment + credit NGO wallet |

## Payments
Leave `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` blank in `.env` to run in **MOCK mode**
(payments auto-succeed, no real charge). Add real **test** keys from the Razorpay dashboard
to switch to live verification — no code change needed.
