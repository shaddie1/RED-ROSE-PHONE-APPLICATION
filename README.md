# 🌹 Red Rose Laundry — Backend API

FastAPI + PostgreSQL backend with **M-Pesa Daraja STK Push** payment integration.

---

## Project Structure

```
redrose-backend/
├── app/
│   ├── main.py                   # FastAPI app entry point
│   ├── core/
│   │   └── config.py             # Settings (reads .env)
│   ├── db/
│   │   └── database.py           # Async SQLAlchemy engine + session
│   ├── models/
│   │   └── models.py             # Order, Payment ORM models
│   ├── schemas/
│   │   └── schemas.py            # Pydantic request/response models
│   ├── services/
│   │   ├── mpesa.py              # ★ Daraja STK Push service
│   │   └── order_service.py      # Order creation + pricing
│   └── api/routes/
│       ├── orders.py             # Order endpoints
│       └── payments.py           # STK Push + callback endpoints
├── requirements.txt
└── .env.example
```

---

## 1. Setup

```bash
# Clone & enter project
cd redrose-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
nano .env
```

---

## 2. Get Safaricom Daraja Credentials

### Step-by-step:

1. Go to **https://developer.safaricom.co.ke** and create an account
2. Create a new App → select **Lipa Na M-Pesa Sandbox**
3. Copy your **Consumer Key** and **Consumer Secret** → paste into `.env`
4. Go to **APIs → Lipa Na M-Pesa Online → Simulate**
5. Use the sandbox shortcode **`174379`** and passkey from the portal

### .env fields to fill:
```env
MPESA_CONSUMER_KEY=abc123...
MPESA_CONSUMER_SECRET=xyz789...
MPESA_SHORTCODE=174379            # Use your real Paybill in production
MPESA_PASSKEY=bfb279f9aa9bdbcf...# From Daraja portal
MPESA_CALLBACK_URL=https://yourdomain.com/api/v1/payments/mpesa/callback
```

> ⚠️ **Callback URL must be HTTPS and publicly reachable.**  
> For local dev, use **ngrok**: `ngrok http 8000` → copy the https URL.

---

## 3. Run the API

```bash
# Start PostgreSQL (Docker one-liner)
docker run -d --name redrose-pg \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=redrose_db \
  -p 5432:5432 postgres:16

# Run FastAPI
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for interactive Swagger UI.

---

## 4. API Endpoints

### Orders

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/orders/` | Create new order |
| GET | `/api/v1/orders/{id}` | Get order by ID |
| GET | `/api/v1/orders/ref/{ref}` | Get by ref e.g. `RRL-0526-AB3K` |
| GET | `/api/v1/orders/customer/{phone}` | List customer orders |

### Payments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/payments/stk-push` | **Trigger M-Pesa STK Push** |
| POST | `/api/v1/payments/mpesa/callback` | Safaricom posts result here |
| GET | `/api/v1/payments/{payment_id}` | Poll payment status |
| GET | `/api/v1/payments/stk/query/{checkout_id}` | Manual Daraja status check |

---

## 5. Full Payment Flow (Code to Code)

### Step 1 — Frontend creates order
```javascript
const order = await fetch('/api/v1/orders/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    customer_name: 'John Mwangi',
    customer_phone: '0712345678',
    customer_address: 'Lavington, Nairobi',
    service_type: 'laundry',       // laundry | carpet | sofa | curtains
    quantity: 2,
    size: 'medium',                // small | medium | large | extra_large
    pickup_date: '2026-05-25T08:00:00',
    notes: 'Handle delicate fabrics carefully'
  })
}).then(r => r.json());

console.log(order.ref);   // "RRL-0526-AB3K"
console.log(order.amount); // 1600
```

### Step 2 — Frontend triggers STK Push
```javascript
const payment = await fetch('/api/v1/payments/stk-push', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    order_id: order.id,
    phone_number: '0712345678'   // Also accepts 254712345678
  })
}).then(r => r.json());

// payment_id is used to poll for status
const { payment_id, customer_message } = payment;
// customer_message → "Success. Request accepted for processing"
```

### Step 3 — Frontend polls for status (every 3 seconds)
```javascript
async function pollPaymentStatus(paymentId, maxAttempts = 20) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise(r => setTimeout(r, 3000));  // wait 3s

    const p = await fetch(`/api/v1/payments/${paymentId}`).then(r => r.json());

    if (p.status === 'paid') {
      console.log('✅ Paid! M-Pesa receipt:', p.mpesa_receipt_number);
      return p;
    }
    if (p.status === 'failed') {
      console.log('❌ Payment failed:', p.result_desc);
      return p;
    }
    // status === 'stk_sent' → still waiting for customer to enter PIN
  }
  // After ~60s, manually query Daraja as fallback
  return await fetch(`/api/v1/payments/stk/query/${checkoutRequestId}`).then(r => r.json());
}
```

---

## 6. STK Push Result Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | **Success — Payment received** | Mark order confirmed, send SMS |
| `1032` | Customer cancelled the prompt | Ask to retry |
| `1037` | Timeout — no response | Ask to retry |
| `2001` | Wrong PIN entered | Ask to retry |
| Other | Generic failure | Show error, allow retry |

---

## 7. Production Checklist

- [ ] Set `MPESA_ENV=production` in `.env`
- [ ] Replace sandbox shortcode with your live **Paybill / Till number**
- [ ] Get live **Passkey** from Safaricom Business portal
- [ ] Callback URL is HTTPS (deploy behind nginx + Let's Encrypt)
- [ ] Lock CORS `allow_origins` to your app domain
- [ ] Add JWT authentication to order/payment routes
- [ ] Set up Alembic migrations instead of `init_db()`
- [ ] Wire in Africa's Talking for SMS confirmations
- [ ] Add APScheduler job to auto-cancel unpaid orders after 30 min

---

## 8. Add SMS with Africa's Talking (Optional)

```bash
pip install africastalking
```

```python
# In app/services/mpesa.py → send_confirmation_sms()
import africastalking

africastalking.initialize(
    username="your_username",
    api_key="your_at_api_key"
)
sms = africastalking.SMS

def send_sms(phone: str, receipt: str, amount: float):
    sms.send(
        f"Red Rose Laundry: Payment of KES {amount:.0f} received. "
        f"M-Pesa receipt {receipt}. We will collect your items shortly! "
        f"Track order at redrose.co.ke",
        [f"+{phone}"]
    )
```
