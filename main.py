import logging
import uuid
import uvicorn
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from fastapi import APIRouter, Request, Response
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from fastapi import FastAPI
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

logger = logging.getLogger()


GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("CLIENT_ID"),
        "client_secret": os.getenv("CLIENT_SECRET"),
        "redirect_uris": [
            os.getenv("REDIRECT_URI"),
        ],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

USER_CREDENTIALS = {
    # example user
    "rohitthakre369@gmail.com": {
        "access_token": None,
        "refresh_token": None,
        "token_expiry": None,
        "channel_id": None,
        "resource_id": None,
    }
}


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/google-calendar/auth")
async def auth_google():
    print(os.getenv("REDIRECT_URI"))
    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=os.getenv("REDIRECT_URI"),
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent", access_type="offline", include_granted_scopes="true"
    )
    return RedirectResponse(auth_url)


@app.get("/google-calendar/callback")
async def callback(request: Request):
    code = request.query_params.get("code")

    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=["https://www.googleapis.com/auth/calendar"],
        redirect_uri=os.getenv("REDIRECT_URI"),
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials

    USER_CREDENTIALS["rohitthakre369@gmail.com"] = {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_expiry": credentials.expiry,
    }
    # Step 2: Build service
    creds = Credentials(
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        expiry=credentials.expiry,
    )
    service = build("calendar", "v3", credentials=creds)

    channel = (
        service.events()
        .watch(
            calendarId="primary",
            body={
                "id": str(uuid.uuid4()),  # your own unique channel ID
                "type": "web_hook",
                "address": os.getenv("GOOGLE_WEBHOOK_URI"),  # url should be https
                "token": "rohitthakre369@gmail.com",  # optional, shows up in X-Goog-Channel-Token
            },
        )
        .execute()
    )

    # uncomment this when we want to stop the channel
    # service.channels().stop(
    #     body={
    #         "id": channel["id"],
    #         "resourceId": channel["resourceId"],
    #     }
    # ).execute()

    # Save: channel["id"], channel["resourceId"]
    USER_CREDENTIALS["rohitthakre369@gmail.com"]["channel_id"] = channel["id"]
    USER_CREDENTIALS["rohitthakre369@gmail.com"]["resource_id"] = channel["resourceId"]
    logger.info(f"channel: {channel}")

    # Redirect to the home page after successful authentication
    return RedirectResponse(url=os.getenv("HOME_URI"))


@app.post("/google-calendar/webhook")
async def google_calendar_webhook(request: Request):
    headers = request.headers

    # Google sends these:
    channel_id = headers.get("X-Goog-Channel-ID")
    resource_id = headers.get("X-Goog-Resource-ID")
    user_token = headers.get(
        "X-Goog-Channel-Token"
    )  # Optional: we can use this to identify user

    # Step 1: Lookup user by channel_id or token
    # user = get_user_by_channel_id(channel_id)
    user = USER_CREDENTIALS["rohitthakre369@gmail.com"]
    if not user:
        return Response(status_code=404)

    # Step 2: Build service
    creds = Credentials(
        token=user["access_token"],
        refresh_token=user["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("CLIENT_ID"),
        client_secret=os.getenv("CLIENT_SECRET"),
        expiry=user["token_expiry"],
    )
    service = build("calendar", "v3", credentials=creds)

    # Step 3: Fetch changed events (you may need to cache syncToken per user)
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            maxResults=20,
            singleEvents=True,
            orderBy="updated",
        )
        .execute()
    )
    logger.info(f"events_result: {events_result}")

    for event in events_result.get("items", []):
        logger.info(f"event:==== {event}")
        # enrich_event_if_needed(service, event)

    return Response(status_code=200)


# if __name__ == "__main__":
#     uvicorn.run(app, host="localhost", port=8000)
