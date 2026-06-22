from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

from app.database import SessionLocal, get_db, engine, Base
from app.models import TransactionRecord, TransactionStatus
from app.services.state_manager import ChatbotStateHandler
from app.services.green_api import GreenAPIClient
from app.services.meter_api import MeterManagementAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure tables exist on startup
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize external service clients
whatsapp_client = GreenAPIClient()
meter_client = MeterManagementAPI()

@app.post("/webhook/greenapi")
async def green_api_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives incoming messages from WhatsApp via Green API."""
    
    # 1. Extract the raw JSON payload first
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    # 2. Process the state manager logic securely
    try:
        # Accept both incoming texts and messages you send to yourself
        if payload.get("typeWebhook") in ["incomingMessageReceived", "outgoingMessageReceived"]:
            message_data = payload.get("messageData", {})
            type_message = message_data.get("typeMessage")
            
            sender_data = payload.get("senderData", {})
            sender = sender_data.get("sender")
            
            # Extract the user's name and grab the first word to be friendly
            raw_name = sender_data.get("senderName") or sender_data.get("senderContactName") or "there"
            first_name = raw_name.split()[0]
            
            text = None
            # Check if it's a normal text or an extended text
            if type_message == "textMessage":
                text = message_data.get("textMessageData", {}).get("textMessage")
            elif type_message == "extendedTextMessage":
                text = message_data.get("extendedTextMessageData", {}).get("text")
                
            if sender and text:
                logger.info(f"Received message from {sender} ({first_name}): {text}")
                
                # Hand data over to your active state machine for normal user flow
                handler = ChatbotStateHandler(db, sender, text, first_name)
                handler.process()
                    
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/webhook/paynow")
async def paynow_webhook(request: Request):
    """Receives background payment updates from Paynow."""
    data = await request.form()
    
    reference = data.get("reference")
    paynow_reference = data.get("paynowreference") 
    status = data.get("status")
    
    # Open database session to find who made this payment
    db = SessionLocal() 
    transaction = db.query(TransactionRecord).filter_by(reference_number=reference).first()
    
    if not transaction:
        db.close()
        return {"status": "ignored", "reason": "transaction not found"}

    # Use the exact Enum from models.py
    if status == "Paid" and transaction.status != TransactionStatus.SUCCESSFUL: 
        # 1. Update the database record
        transaction.status = TransactionStatus.SUCCESSFUL
        db.commit()

        # 2. Trigger the Zhongyi API to push top-up directly to the edge device
        recharge_data = meter_client.process_recharge(
            meter_no=transaction.meter_number, 
            amount_usd=transaction.amount_usd,
            pay_id=paynow_reference  
        )

        # 3. Send the confirmation back to the user via WhatsApp
        if recharge_data["status"] == "success":
            # We still save the token for our own database records
            token = recharge_data["display_token"]
            volume = recharge_data["volume_kg"]
            
            transaction.token = token
            db.commit()
            
            msg = (
                f"🎉 *Payment Successful!*\n\n"
                f"Gas Volume: {volume} kg\n"
                f"Amount Paid: USD {transaction.amount_usd:.2f}\n"
                f"Meter: {transaction.meter_number}\n\n"
                f"⚡ Your account has been credited. \n\n"
                f"⏳ *Note:* Your meter will update automatically within 24 hours to save battery.\n\n"
                f"🔥 *Need gas instantly?*\n"
                f"Press and hold the button on your physical meter for 3 seconds to wake it up and download your credit right now."
            )
            whatsapp_client.send_message(transaction.whatsapp_num, msg)
        else:
            # Fallback if the token generation fails but they already paid
            error_msg = f"⚠️ Your payment of USD {transaction.amount_usd:.2f} was successful, but we had trouble reaching the meter network. Please contact support with Ref: {reference}."
            whatsapp_client.send_message(transaction.whatsapp_num, error_msg)
            
    # Use the exact Enum from models.py
    elif status in ["Cancelled", "Failed"] and transaction.status != TransactionStatus.FAILED:
        transaction.status = TransactionStatus.FAILED
        db.commit()
        
        msg = f"❌ Your payment for Ref: {reference} was declined or cancelled. Please reply with *0* to start over."
        whatsapp_client.send_message(transaction.whatsapp_num, msg)
        
    db.close()
    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)