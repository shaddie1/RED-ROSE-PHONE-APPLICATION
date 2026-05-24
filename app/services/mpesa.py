"""
M-Pesa Daraja STK Push Service
================================
Wraps Safaricom Daraja API v2 endpoints:
  - /oauth/v1/generate?grant_type=client_credentials  → access token
  - /mpesa/stkpush/v1/processrequest                  → initiate STK Push
  - /mpesa/stkpushquery/v1/query                      → query payment status
"""
import base64
import hashlib
import logging
from datetime import datetime, timedelta

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MpesaService:
    """Singleton-style service; share one httpx.AsyncClient per app lifetime."""

    def __init__(self):
        self._token: str | None = None
        self._token_expires_at: datetime = datetime.utcnow()
        self._client = httpx.AsyncClient(timeout=30)

    # ─────────────────────────────────────────────────────────
    # 1. ACCESS TOKEN
    # ─────────────────────────────────────────────────────────

    async def get_access_token(self) -> str:
        """
        Fetch (or return cached) OAuth2 bearer token from Daraja.
        Token is valid for 3600 s; we refresh 60 s early.
        """
        if self._token and datetime.utcnow() < self._token_expires_at:
            return self._token

        credentials = f"{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        url = f"{settings.MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
        resp = await self._client.get(
            url, headers={"Authorization": f"Basic {encoded}"}
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data["access_token"]
        self._token_expires_at = datetime.utcnow() + timedelta(
            seconds=int(data.get("expires_in", 3600)) - 60
        )
        logger.info("M-Pesa access token refreshed")
        return self._token

    # ─────────────────────────────────────────────────────────
    # 2. GENERATE STK PASSWORD
    # ─────────────────────────────────────────────────────────

    def _generate_password(self) -> tuple[str, str]:
        """
        Returns (password, timestamp) pair.
        password = base64( shortcode + passkey + timestamp )
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
        password = base64.b64encode(raw.encode()).decode()
        return password, timestamp

    # ─────────────────────────────────────────────────────────
    # 3. INITIATE STK PUSH
    # ─────────────────────────────────────────────────────────

    async def stk_push(
        self,
        phone_number: str,   # Must be 254XXXXXXXXX format
        amount: int,         # KES — Safaricom requires integer
        order_ref: str,      # Short reference shown in M-Pesa message
        description: str = "Red Rose Laundry Payment",
    ) -> dict:
        """
        Send STK Push request to customer's phone.

        Returns Daraja's raw response dict:
        {
            "MerchantRequestID": "...",
            "CheckoutRequestID": "...",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing"
        }
        ResponseCode == "0" means the push was sent successfully.
        Actual payment confirmation arrives via the callback URL.
        """
        token = await self.get_access_token()
        password, timestamp = self._generate_password()

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",  # or "CustomerBuyGoodsOnline" for Till
            "Amount": int(amount),                       # Must be integer
            "PartyA": phone_number,                      # Customer phone 254XXXXXXXXX
            "PartyB": settings.MPESA_SHORTCODE,          # Your shortcode
            "PhoneNumber": phone_number,                 # Same as PartyA for STK
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": order_ref[:12],          # Max 12 chars
            "TransactionDesc": description[:13],         # Max 13 chars
        }

        url = f"{settings.MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
        resp = await self._client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        data = resp.json()
        logger.info(
            "STK Push sent | phone=%s | order=%s | response=%s",
            phone_number, order_ref, data,
        )

        if data.get("ResponseCode") != "0":
            raise MpesaError(
                f"STK Push failed: {data.get('ResponseDescription', 'Unknown error')}"
            )

        return data

    # ─────────────────────────────────────────────────────────
    # 4. QUERY STK PUSH STATUS
    # ─────────────────────────────────────────────────────────

    async def query_stk_status(self, checkout_request_id: str) -> dict:
        """
        Manually poll the status of a pending STK Push.
        Use this if the callback hasn't arrived within ~30 s.

        Returns dict with ResultCode:
          0  = Success (paid)
          1032 = Request cancelled by user
          1037 = Timeout
          Other = Failed
        """
        token = await self.get_access_token()
        password, timestamp = self._generate_password()

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        url = f"{settings.MPESA_BASE_URL}/mpesa/stkpushquery/v1/query"
        resp = await self._client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        data = resp.json()
        logger.info("STK status query | checkout_id=%s | result=%s", checkout_request_id, data)
        return data

    async def close(self):
        await self._client.aclose()


class MpesaError(Exception):
    """Raised when Daraja returns a non-success response."""
    pass


# Module-level singleton — import this everywhere
mpesa_service = MpesaService()
