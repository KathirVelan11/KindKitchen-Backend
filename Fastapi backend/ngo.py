from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from main import conn, cursor
import oauth2 as oauth2

router = APIRouter()

class NGOOut(BaseModel):
    ngoid: int
    name: str

class NGOResponse(BaseModel):
    count: int
    ngos: List[NGOOut]

@router.get("/", response_model=NGOResponse)
#get_current_user: int = Depends(oauth2.get_current_user)
def list_all_ngos():
    try:
        cursor.execute("SELECT ngoid, name FROM NGOs ORDER BY name;")
        ngos = cursor.fetchall()
        return {
            "count": len(ngos),
            "ngos": ngos
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-user/{user_id}")
def get_ngo_by_user(user_id: int):
    """Resolve the NGO profile (and live wallet balance) for a logged-in user."""
    cursor.execute("SELECT ngoid, name FROM NGOs WHERE userid = %s;", (user_id,))
    ngo = cursor.fetchone()
    if not ngo:
        raise HTTPException(status_code=404, detail="NGO profile not found for this user")
    cursor.execute("SELECT walletbalance FROM Wallets WHERE ngoid = %s;", (ngo["ngoid"],))
    wallet = cursor.fetchone()
    balance = float(wallet["walletbalance"]) if wallet else 0.0
    return {"ngoid": ngo["ngoid"], "name": ngo["name"], "walletbalance": balance}


@router.get("/{ngo_id}/wallet")
def get_ngo_wallet(ngo_id: int):
    cursor.execute("SELECT walletbalance FROM Wallets WHERE ngoid = %s;", (ngo_id,))
    wallet = cursor.fetchone()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"ngoid": ngo_id, "walletbalance": float(wallet["walletbalance"])}
