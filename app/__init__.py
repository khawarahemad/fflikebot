# app/__init__.py

from flask import Flask, request
import os
import logging
from datetime import timedelta

# Importations des modules au même niveau dans le dossier app/
from .token_manager import TokenCache, get_headers # Notez le '.' pour l'import relatif
from .like_routes import like_bp, initialize_routes # Importez le Blueprint et la fonction d'initialisation

# Configuration de base de l'application
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration des serveurs
SERVERS = {
    "EUROPE": os.getenv("EUROPE_SERVER", "https://clientbp.ggblueshark.com"),
    "IND": os.getenv("IND_SERVER", "https://client.ind.freefiremobile.com"),
    "BR": os.getenv("BR_SERVER", "https://client.us.freefiremobile.com"),
}

# Initialisation du cache de tokens
# Le AUTH_URL n'est pas utilisé directement ici, mais dans TokenCache. C'est OK.
token_cache = TokenCache(servers_config=SERVERS) # Passez la config des serveurs au TokenCache

# Middleware pour gérer les requêtes
@app.before_request
def handle_chunking():
    transfer_encoding = request.headers.get("Transfer-Encoding", "")
    if "chunked" in transfer_encoding.lower():
        request.environ["wsgi.input_terminated"] = True

# Initialiser et enregistrer les routes
# Passez l'instance de l'application, la configuration des serveurs et l'instance du token_cache
initialize_routes(app, SERVERS, token_cache)