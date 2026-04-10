import os
import json
import anthropic
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- INITIALIZATION ---
load_dotenv()
app = Flask(__name__)

# Validate API key at startup — fail fast with a clear message
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    raise EnvironmentError("ANTHROPIC_API_KEY is not set in the environment or .env file.")

client = anthropic.Anthropic(api_key=api_key)

# --- HELPER FUNCTIONS ---
def load_vault():
    """Load vault data from data.json with error handling."""
    if not os.path.exists('data.json'):
        raise FileNotFoundError("data.json not found. Please create it before starting the server.")
    with open('data.json', 'r') as f:
        return json.load(f)

def save_vault(data):
    """Persist vault data to data.json."""
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)

# --- THE MANAGER ENDPOINT ---
@app.route('/manager', methods=['POST'])
def manager():
    # FIX: Guard against missing or non-JSON body
    incoming = request.get_json(silent=True)
    if not incoming:
        return jsonify({"status": "error", "message": "Request body must be valid JSON."}), 400

    # FIX: Preserve original query for AI; use lowercase only for keyword matching
    raw_query = incoming.get("query", "").strip()
    if not raw_query:
        return jsonify({"status": "error", "message": "Field 'query' is required and cannot be empty."}), 400

    query_lower = raw_query.lower()

    # FIX: Wrap vault loading in try/except to return a clean error if file is missing
    try:
        vault = load_vault()
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # 1. Financial Module — keyword match on lowercased query
    if any(word in query_lower for word in ["balance", "money", "vault"]):
        return jsonify({
            "status": "success",
            "source": "DATABASE",
            "response": (
                f"The {vault['company_name']} vault currently holds "
                f"{vault['balance']} {vault['currency']}."
            )
        })

    # 2. Administrative Module — pass original (non-lowercased) query to AI
    try:
        system_context = (
            f"You are the Chief AI Officer of {vault['company_name']}. "
            "Be professional and brief."
        )

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_context,
            messages=[
                {"role": "user", "content": raw_query}  # FIX: use original casing
            ]
        )

        # FIX: Guard against empty content blocks from the API
        if not message.content:
            return jsonify({"status": "error", "message": "AI returned an empty response."}), 500

        return jsonify({
            "status": "success",
            "source": "AI_BRAIN",
            "response": message.content[0].text
        })

    except anthropic.APIConnectionError:
        return jsonify({"status": "error", "message": "Could not connect to the Anthropic API."}), 503
    except anthropic.RateLimitError:
        return jsonify({"status": "error", "message": "API rate limit reached. Please retry shortly."}), 429
    except anthropic.APIStatusError as e:
        return jsonify({"status": "error", "message": f"Anthropic API error: {e.message}"}), e.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Unexpected error: {str(e)}"}), 500


if __name__ == '__main__':
    # FIX: debug=True disabled — never use in production/cloud deployments
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
