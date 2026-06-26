from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Literal, Optional
import oauth2 as oauth2
# Reuse the single shared DB connection/cursor created in main.py
from main import conn, cursor

router = APIRouter()

# Shared Model
class PaymentRequest(BaseModel):
    toUserID: int
    amount: float
    payment_method: Literal["Credit Card", "Debit Card", "UPI", "Cash", "Bank Transfer", "Wallet"]
    status: Literal["Success", "Failed", "Pending"]

# Validators
def validate_user(table: str, user_id: int):
    cursor.execute(f"SELECT * FROM {table} WHERE {table[:-1]}ID = %s;", (user_id,))
    return cursor.fetchone()

# 🔁 Donor → NGO
@router.post("/donor-to-ngo/{donor_id}", status_code=status.HTTP_201_CREATED)
def donor_to_ngo_payment(donor_id: int, payment: PaymentRequest,get_current_user:int=Depends(oauth2.get_current_user)):
    ngo_id = payment.toUserID

    # Fetch Donor and NGO records
    cursor.execute("SELECT userid FROM Donors WHERE donorid = %s;", (donor_id,))
    donor_user_row = cursor.fetchone()
    if not donor_user_row:
        raise HTTPException(status_code=404, detail=f"Donor {donor_id} not found")

    cursor.execute("SELECT userid FROM NGOs WHERE ngoid = %s;", (ngo_id,))
    ngo_user_row = cursor.fetchone()
    if not ngo_user_row:
        raise HTTPException(status_code=404, detail=f"NGO {ngo_id} not found")

    donor_user_id = donor_user_row["userid"]
    ngo_user_id = ngo_user_row["userid"]

    if payment.payment_method == "Wallet":
        raise HTTPException(status_code=400, detail="❌ Donors cannot use 'Wallet' as payment method")

    try:
        # Step 1: Record the payment using userIDs
        cursor.execute("""
            INSERT INTO Payments (fromUserID, toUserID, Amount, PaymentMethod, TransactionStatus)
            VALUES (%s, %s, %s, %s, %s) RETURNING *;
        """, (donor_user_id, ngo_user_id, payment.amount, payment.payment_method, payment.status))
        payment_record = cursor.fetchone()

        # Step 2: Update NGO Wallet if payment successful
        if payment.status == "Success":
            cursor.execute("""
                UPDATE Wallets 
                SET walletbalance = walletbalance + %s
                WHERE ngoid = %s;
            """, (payment.amount, ngo_id))

            cursor.execute("SELECT walletbalance FROM Wallets WHERE ngoid = %s;", (ngo_id,))
            updated_balance = cursor.fetchone()["walletbalance"]

            cursor.execute("""
                UPDATE NGOs
                SET walletBalance = %s
                WHERE ngoid = %s;
            """, (updated_balance, ngo_id))

        conn.commit()
        return {
            "message": "✅ Donor → NGO payment recorded using userIDs",
            "data": payment_record
        }

    except Exception as e:
        conn.rollback()
        print("❌ DB error occurred:", e)  # ← Add this
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


# ======================================================================
# Razorpay payment gateway (with automatic MOCK fallback when no keys)
# ======================================================================
import os
import uuid

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
GATEWAY_LIVE = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)

_razor_client = None
if GATEWAY_LIVE:
    try:
        import razorpay
        _razor_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        print("✅ Razorpay gateway: LIVE mode")
    except Exception as e:
        print("⚠️ Razorpay init failed, falling back to MOCK:", e)
        GATEWAY_LIVE = False
else:
    print("ℹ️ Razorpay gateway: MOCK mode (set RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in .env to go live)")


class CreateOrderRequest(BaseModel):
    amount: float  # rupees


@router.post("/create-order")
def create_payment_order(req: CreateOrderRequest):
    """Create a gateway order the client (Razorpay Checkout) can pay against.
    In MOCK mode it returns a fake order so the whole flow works without keys."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")
    amount_paise = int(round(req.amount * 100))
    if GATEWAY_LIVE:
        order = _razor_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1,
        })
        return {
            "mock": False,
            "order_id": order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "key_id": RAZORPAY_KEY_ID,
        }
    # MOCK
    return {
        "mock": True,
        "order_id": f"order_mock_{uuid.uuid4().hex[:16]}",
        "amount": amount_paise,
        "currency": "INR",
        "key_id": "mock_key",
    }


class VerifyPaymentRequest(BaseModel):
    donor_id: int
    ngo_id: int
    amount: float
    payment_method: str = "UPI"
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    razorpay_signature: Optional[str] = None


@router.post("/verify", status_code=status.HTTP_201_CREATED)
def verify_and_record_payment(req: VerifyPaymentRequest):
    """Verify the gateway signature (LIVE) or auto-accept (MOCK), then record the
    Donor → NGO payment and credit the NGO wallet — same effect as donor-to-ngo."""
    # 1. Verify
    if GATEWAY_LIVE:
        if not (req.razorpay_order_id and req.razorpay_payment_id and req.razorpay_signature):
            raise HTTPException(status_code=400, detail="Missing Razorpay verification fields")
        try:
            _razor_client.utility.verify_payment_signature({
                "razorpay_order_id": req.razorpay_order_id,
                "razorpay_payment_id": req.razorpay_payment_id,
                "razorpay_signature": req.razorpay_signature,
            })
        except Exception:
            raise HTTPException(status_code=400, detail="❌ Payment signature verification failed")

    # 2. Resolve donor + ngo userIDs
    cursor.execute("SELECT userid FROM Donors WHERE donorid = %s;", (req.donor_id,))
    donor_row = cursor.fetchone()
    if not donor_row:
        raise HTTPException(status_code=404, detail=f"Donor {req.donor_id} not found")
    cursor.execute("SELECT userid FROM NGOs WHERE ngoid = %s;", (req.ngo_id,))
    ngo_row = cursor.fetchone()
    if not ngo_row:
        raise HTTPException(status_code=404, detail=f"NGO {req.ngo_id} not found")

    try:
        # 3. Record payment
        cursor.execute("""
            INSERT INTO Payments (fromUserID, toUserID, Amount, PaymentMethod, TransactionStatus)
            VALUES (%s, %s, %s, %s, 'Success') RETURNING *;
        """, (donor_row["userid"], ngo_row["userid"], req.amount, req.payment_method))
        payment_record = cursor.fetchone()

        # 4. Credit NGO wallet
        cursor.execute("UPDATE Wallets SET walletbalance = walletbalance + %s WHERE ngoid = %s;",
                       (req.amount, req.ngo_id))
        cursor.execute("SELECT walletbalance FROM Wallets WHERE ngoid = %s;", (req.ngo_id,))
        updated = cursor.fetchone()["walletbalance"]
        cursor.execute("UPDATE NGOs SET walletBalance = %s WHERE ngoid = %s;", (updated, req.ngo_id))

        conn.commit()
        return {
            "message": "✅ Payment verified and recorded",
            "mode": "live" if GATEWAY_LIVE else "mock",
            "new_wallet_balance": float(updated),
            "payment": payment_record,
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
