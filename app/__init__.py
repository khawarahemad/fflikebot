# app/__init__.py

from flask import Flask, request
import os
import logging
from datetime import timedelta


from .token_manager import TokenCache, get_headers 
from .like_routes import like_bp, initialize_routes 

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SERVERS = {
    "EUROPE": os.getenv("EUROPE_SERVER", "https://clientbp.ggblueshark.com"),
    "IND": os.getenv("IND_SERVER", "https://client.ind.freefiremobile.com"),
    "BR": os.getenv("BR_SERVER", "https://client.us.freefiremobile.com"),
}


token_cache = TokenCache(servers_config=SERVERS) 

# Middleware pour gérer les requêtes
@app.before_request
def handle_chunking():
    transfer_encoding = request.headers.get("Transfer-Encoding", "")
    if "chunked" in transfer_encoding.lower():
        request.environ["wsgi.input_terminated"] = True

initialize_routes(app, SERVERS, token_cache)