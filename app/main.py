from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

from app.database import get_db, engine, Base
from app.services.state_manager import ChatbotStateHandler

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

@app.post("/webhook/greenapi")
async def green_api_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives incoming messages from WhatsApp via Green API."""
    
    # 1. Extract the raw JSON payload first
    try:
        payload = await request.json()
    except Exception as e:
        print(f"Error parsing JSON: {e}")
        return {"status": "error", "message": "Invalid JSON"}

    # 2. Print raw webhook structure to the terminal console
    print("\n====== RAW WEBHOOK DATA ======")
    print(payload)
    print("==============================\n")

    # 3. Process the state manager logic securely
    try:
        # Accept both incoming texts and messages you send to yourself
        if payload.get("typeWebhook") in ["incomingMessageReceived", "outgoingMessageReceived"]:
            message_data = payload.get("messageData", {})
            type_message = message_data.get("typeMessage")
            
            text = None
            sender = payload.get("senderData", {}).get("sender")

            # Check if it's a normal text or an extended text
            if type_message == "textMessage":
                text = message_data.get("textMessageData", {}).get("textMessage")
            elif type_message == "extendedTextMessage":
                text = message_data.get("extendedTextMessageData", {}).get("text")
                
            if sender and text:
                logger.info(f"Received message from {sender}: {text}")
                
                # Hand data over to your active state machine
                handler = ChatbotStateHandler(db, sender, text)
                handler.process()
                    
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)