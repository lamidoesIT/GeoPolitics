import os
import random
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash

from database.repositories import CountryRepository, UserRepository, GameSessionRepository
from database.seed_countries import WORLD_COUNTRIES_SEED
from models.domain_models import CountryTerritory, HumanPlayer, NPCPlayer, BattleEngine
from services.ai_commentary_service import AICommentaryService

app = Flask(__name__)
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    # Generated fresh each process start if .env is missing — sessions won't
    # survive a restart, but no fixed/guessable secret ever ships in the code.
    import secrets as _secrets
    _secret_key = _secrets.token_hex(32)
    print("WARNING: SECRET_KEY not set in environment — using a temporary random key for this run only.")
app.secret_key = _secret_key

country_repo = CountryRepository()
user_repo = UserRepository()
game_repo = GameSessionRepository()

# Seed Worldometer Country Data on startup
country_repo.seed_if_empty(WORLD_COUNTRIES_SEED)

NPC_PERSONALITIES = [
    "Calculated Expansionist",
    "Iron Defense Doctrine",
    "Opportunistic Blitz",
    "Attritional Strategist"
]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return jsonify({"error": "Authentication required. Visitors have read-only spectator access."}), 401
        return f(*args, **kwargs)
    return decorated


def verify_game_owner(game_doc: dict):
    """Enforces Access Control: Any visitor can view a shared game link, but only the logged-in owner can play a turn."""
    current_user = session.get("username")
    if not current_user or current_user != game_doc["owner_username"]:
        return False
    return True


@app.route("/")
def index():
    return render_template("index.html")


# ---------------- AUTHENTICATION ROUTES ---------------- #

@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "Username must be >= 3 chars and password >= 6 chars."}), 400
    if user_repo.find_by_username(username):
        return jsonify({"error": "Username already exists."}), 409

    user_repo.create_user(username, generate_password_hash(password))
    session["username"] = username
    return jsonify({"username": username, "message": "Account created successfully."})


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = user_repo.find_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    session["username"] = username
    return jsonify({"username": username})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})


@app.route("/api/auth/me", methods=["GET"])
def current_user():
    return jsonify({"username": session.get("username")})


# ---------------- SEARCH, FILTER & ANALYTICS ROUTES ---------------- #

@app.route("/api/countries", methods=["GET"])
def list_countries():
    search = request.args.get("search", "")
    min_tier = int(request.args.get("min_tier", 1))
    return jsonify(country_repo.get_all(search=search, min_tier=min_tier))


@app.route("/api/games", methods=["GET"])
def list_games():
    status = request.args.get("status", "ALL")
    search = request.args.get("search", "")
    owner_only = request.args.get("mine", "false") == "true"
    owner = session.get("username") if owner_only else None
    return jsonify(game_repo.list_sessions(owner=owner, status=status, search=search))


@app.route("/api/analytics", methods=["GET"])
def analytics():
    return jsonify(game_repo.get_platform_analytics())


# ---------------- GAME SETUP & STATE ROUTES ---------------- #

@app.route("/api/games/new", methods=["POST"])
@login_required
def create_game():
    data = request.get_json() or {}
    selected_country_name = data.get("country_name")
    all_countries = country_repo.get_all()
    chosen = next((c for c in all_countries if c["name"] == selected_country_name), None)
    if not chosen:
        return jsonify({"error": "Selected country not found in database."}), 400

    # Rule: Select 1 player country + 9 randomly selected NPC countries (10 total)
    remaining_pool = [c for c in all_countries if c["name"] != selected_country_name]
    sampled_npcs = random.sample(remaining_pool, 9)

    username = session["username"]
    human = HumanPlayer(player_id="HUMAN_1", display_name=username, home_country=chosen["name"])
    participants = [human.to_dict()]
    territories = [CountryTerritory(chosen["name"], chosen["population"], "HUMAN_1").to_dict()]

    for idx, npc_country in enumerate(sampled_npcs, start=1):
        npc_id = f"NPC_{idx}"
        personality = NPC_PERSONALITIES[(idx - 1) % len(NPC_PERSONALITIES)]
        npc = NPCPlayer(
            player_id=npc_id,
            display_name=f"Commander {npc_country['name']} (AI)",
            home_country=npc_country["name"],
            personality=personality
        )
        participants.append(npc.to_dict())
        territories.append(CountryTerritory(npc_country["name"], npc_country["population"], npc_id).to_dict())

    # Rule: Randomly decide which player goes first
    turn_order = [p["player_id"] for p in participants]
    random.shuffle(turn_order)

    now_iso = datetime.now(timezone.utc).isoformat()
    state = {
        "owner_username": username,
        "player_country": chosen["name"],
        "status": "ACTIVE",
        "winner_name": None,
        "round_number": 1,
        "turn_index": 0,
        "turn_order": turn_order,
        "current_turn_player_id": turn_order[0],
        "pending_reinforcements": 0,
        "attack_used_this_turn": False,
        "active_attack": None,  # Tracks ongoing multi-roll battle
        "participants": participants,
        "territories": territories,
        "event_feed": [{
            "timestamp": now_iso,
            "type": "SYSTEM",
            "title": "New Geopolitical Theatre Initialized",
            "detail": f"10 nations mobilized. Random draw selected {turn_order[0]} to open Round 1."
        }],
        "created_at": now_iso,
        "updated_at": now_iso
    }

    game_id = game_repo.create_session(state)
    user_repo.increment_stats(username, won=False)
    state["game_id"] = game_id
    return jsonify(state), 201


@app.route("/api/games/<game_id>", methods=["GET"])
def get_game(game_id):
    """Publicly viewable endpoint so shared links work for visitors in Spectator Mode."""
    game = game_repo.get_session(game_id)
    if not game:
        return jsonify({"error": "Game session not found."}), 404
    game["can_play"] = verify_game_owner(game)
    return jsonify(game)


# ---------------- HUMAN TURN ACTIONS ---------------- #

@app.route("/api/games/<game_id>/reinforce", methods=["POST"])
@login_required
def allocate_reinforcements(game_id):
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized: Only the session owner can allocate reinforcements."}), 403
    if game["current_turn_player_id"] != "HUMAN_1" or game["pending_reinforcements"] <= 0:
        return jsonify({"error": "No pending reinforcements to allocate."}), 400

    data = request.get_json() or {}
    country_name = data.get("country_name")
    amount = int(data.get("amount", 0))

    if amount <= 0 or amount > game["pending_reinforcements"]:
        return jsonify({"error": "Invalid reinforcement amount."}), 400

    target = next((t for t in game["territories"] if t["name"] == country_name and t["owner_id"] == "HUMAN_1"), None)
    if not target:
        return jsonify({"error": "You do not control that territory."}), 400

    target["soldiers"] += amount
    game["pending_reinforcements"] -= amount
    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "REINFORCE",
        "title": f"Reinforcements Deployed (+{amount})",
        "detail": f"{game['owner_username']} deployed +{amount} soldiers to {country_name} (Total: {target['soldiers']})."
    })
    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify(game)


@app.route("/api/games/<game_id>/transfer", methods=["POST"])
@login_required
def transfer_soldiers(game_id):
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized action."}), 403
    if game["current_turn_player_id"] != "HUMAN_1":
        return jsonify({"error": "Wait for your turn to transfer soldiers."}), 400
    if game["active_attack"] is not None:
        return jsonify({"error": "Rule Violation: Cannot transfer soldiers while an attack is in progress."}), 400

    data = request.get_json() or {}
    from_name = data.get("from_country")
    to_name = data.get("to_country")
    amount = int(data.get("amount", 0))

    if from_name == to_name or amount <= 0:
        return jsonify({"error": "Select two distinct controlled countries and a positive transfer amount."}), 400

    src = next((t for t in game["territories"] if t["name"] == from_name and t["owner_id"] == "HUMAN_1"), None)
    dst = next((t for t in game["territories"] if t["name"] == to_name and t["owner_id"] == "HUMAN_1"), None)
    if not src or not dst:
        return jsonify({"error": "Both territories must be under your control."}), 400

    # Rule: A country must retain at least 1 soldier after transfers are completed
    if src["soldiers"] - amount < 1:
        return jsonify({"error": f"{from_name} must retain at least 1 soldier (Max transferable: {src['soldiers'] - 1})."}), 400

    src["soldiers"] -= amount
    dst["soldiers"] += amount
    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "TRANSFER",
        "title": f"Troop Redeployment ({amount} Soldiers)",
        "detail": f"Transferred {amount} soldiers from {from_name} ({src['soldiers']} left) to {to_name} ({dst['soldiers']} total)."
    })
    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify(game)


@app.route("/api/games/<game_id>/attack-roll", methods=["POST"])
@login_required
def attack_roll(game_id):
    """Executes one dice-rolling phase of an attack (Player keeps rolling until conquest, 1 soldier left, or stop)."""
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized: Spectator visitors cannot execute attacks."}), 403
    if game["current_turn_player_id"] != "HUMAN_1":
        return jsonify({"error": "It is not currently your turn."}), 400
    if game["pending_reinforcements"] > 0:
        return jsonify({"error": "Allocate all pending reinforcements before launching an attack."}), 400

    data = request.get_json() or {}
    from_name = data.get("attacker_country")
    to_name = data.get("defender_country")

    # Enforce 1 attack target per turn rule
    if game["active_attack"]:
        if (game["active_attack"]["attacker"] != from_name or game["active_attack"]["defender"] != to_name):
            return jsonify({"error": "You may only attack one target country per turn."}), 400
    elif game["attack_used_this_turn"]:
        return jsonify({"error": "You have already completed your one attack for this turn."}), 400

    att_dict = next((t for t in game["territories"] if t["name"] == from_name and t["owner_id"] == "HUMAN_1"), None)
    def_dict = next((t for t in game["territories"] if t["name"] == to_name and t["owner_id"] != "HUMAN_1"), None)
    if not att_dict or not def_dict:
        return jsonify({"error": "Invalid attacker or defender selection."}), 400
    if att_dict["soldiers"] < 2:
        return jsonify({"error": "You need at least 2 soldiers in the attacking country to roll."}), 400

    attacker_obj = CountryTerritory.from_dict(att_dict)
    defender_obj = CountryTerritory.from_dict(def_dict)

    phase_result = BattleEngine.execute_dice_phase(attacker_obj, defender_obj)
    att_dict.update(attacker_obj.to_dict())
    def_dict.update(defender_obj.to_dict())

    commentary = AICommentaryService.generate_battle_commentary(
        phase_result, game["owner_username"], def_dict["owner_id"]
    )
    phase_result["ai_commentary"] = commentary

    if phase_result["conquered"] or phase_result["attacker_forced_stop"]:
        game["active_attack"] = None
        game["attack_used_this_turn"] = True
    else:
        game["active_attack"] = {"attacker": from_name, "defender": to_name}

    _update_eliminations_and_victory(game)

    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "BATTLE",
        "title": f"Battle Phase: {from_name} vs {to_name}",
        "detail": commentary,
        "dice_data": phase_result
    })
    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify({"game": game, "battle_phase": phase_result})


@app.route("/api/games/<game_id>/stop-attack", methods=["POST"])
@login_required
def stop_attack(game_id):
    """Rule: If a player stops an attack, their turn ends and they retain remaining soldiers in that country."""
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized."}), 403

    game["active_attack"] = None
    game["attack_used_this_turn"] = True
    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "SYSTEM",
        "title": "Attack Halted by Commander",
        "detail": f"{game['owner_username']} called off the assault and ended their turn."
    })
    _advance_turn_pointer(game)
    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify(game)


@app.route("/api/games/<game_id>/end-turn", methods=["POST"])
@login_required
def end_turn(game_id):
    """Skips/ends the current turn and advances to the next active participant."""
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized."}), 403
    if game["current_turn_player_id"] != "HUMAN_1":
        return jsonify({"error": "Not your turn."}), 400

    game["active_attack"] = None
    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "SYSTEM",
        "title": "Turn Completed",
        "detail": f"{game['owner_username']} concluded their turn. Advancing turn order."
    })
    _advance_turn_pointer(game)
    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify(game)


# ---------------- NPC AI TURN SIMULATION ---------------- #

@app.route("/api/games/<game_id>/simulate-npc", methods=["POST"])
@login_required
def simulate_npc_turn(game_id):
    """Executes the current NPC's full turn (Reinforce -> Transfer -> Heuristic Attack -> Justifications)."""
    game = game_repo.get_session(game_id)
    if not game or not verify_game_owner(game):
        return jsonify({"error": "Unauthorized."}), 403
    if game["status"] != "ACTIVE":
        return jsonify(game)

    current_id = game["current_turn_player_id"]
    if current_id == "HUMAN_1":
        return jsonify({"error": "Current turn belongs to the human player."}), 400

    p_dict = next((p for p in game["participants"] if p["player_id"] == current_id), None)
    npc = NPCPlayer(
        player_id=p_dict["player_id"],
        display_name=p_dict["display_name"],
        home_country=p_dict["home_country"],
        personality=p_dict.get("personality", "Calculated Expansionist"),
        eliminated=p_dict["eliminated"]
    )

    all_territories = [CountryTerritory.from_dict(t) for t in game["territories"]]
    my_territories = [t for t in all_territories if t.owner_id == current_id]
    enemy_territories = [t for t in all_territories if t.owner_id != current_id]

    if not my_territories:
        p_dict["eliminated"] = True
        _advance_turn_pointer(game)
        game_repo.update_session(game_id, game)
        game["can_play"] = True
        return jsonify(game)

    npc_logs = []

    # 1. Round 2+ Reinforcements
    if game["pending_reinforcements"] > 0:
        _, reinf_reason = npc.allocate_reinforcements(my_territories, all_territories, game["pending_reinforcements"])
        game["pending_reinforcements"] = 0
        npc_logs.append(reinf_reason)

    # 2. Strategic Troop Transfer
    _, transfer_reason = npc.decide_transfer(my_territories)
    npc_logs.append(transfer_reason)

    # 3. Target Evaluation & Multi-Phase Combat
    att_country, def_country, attack_reason = npc.choose_attack_target(my_territories, enemy_territories)
    npc_logs.append(attack_reason)

    last_battle_phase = None
    if att_country and def_country:
        while att_country.can_attack() and def_country.soldiers > 0:
            keep_going, cont_reason = npc.should_continue_attack(att_country, def_country)
            if not keep_going:
                npc_logs.append(cont_reason)
                break

            phase = BattleEngine.execute_dice_phase(att_country, def_country)
            commentary = AICommentaryService.generate_battle_commentary(
                phase, npc.display_name, def_country.owner_id
            )
            phase["ai_commentary"] = commentary
            last_battle_phase = phase
            npc_logs.append(commentary)

            if phase["conquered"] or phase["attacker_forced_stop"]:
                break

    # Persist updated territory states
    game["territories"] = [t.to_dict() for t in all_territories]
    _update_eliminations_and_victory(game)

    game["event_feed"].insert(0, {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": "NPC_TURN",
        "title": f"{npc.display_name} Executed Turn",
        "detail": " | ".join(npc_logs),
        "dice_data": last_battle_phase
    })
    game["event_feed"] = game["event_feed"][:60]

    if game["status"] == "ACTIVE":
        _advance_turn_pointer(game)

    game_repo.update_session(game_id, game)
    game["can_play"] = True
    return jsonify(game)


def _update_eliminations_and_victory(game: dict):
    """Checks for eliminated players (0 countries) and world conquest (10 countries)."""
    counts = {}
    for t in game["territories"]:
        counts[t["owner_id"]] = counts.get(t["owner_id"], 0) + 1

    for p in game["participants"]:
        if counts.get(p["player_id"], 0) == 0:
            p["eliminated"] = True

    for owner_id, count in counts.items():
        if count == 10:
            game["status"] = "COMPLETED"
            winner = next((p for p in game["participants"] if p["player_id"] == owner_id), None)
            game["winner_name"] = winner["display_name"] if winner else owner_id
            if owner_id == "HUMAN_1":
                user_repo.increment_stats(game["owner_username"], won=True)
            game["event_feed"].insert(0, {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "VICTORY",
                "title": f"🏆 WORLD CONQUEST ACHIEVED BY {game['winner_name']}!",
                "detail": f"{game['winner_name']} now controls all 10 nations on the board!"
            })


def _advance_turn_pointer(game: dict):
    """Advances turn order, skips eliminated players, increments rounds, and awards 2 soldiers/country from Round 2+."""
    if game["status"] != "ACTIVE":
        return

    order = game["turn_order"]
    total_players = len(order)

    for _ in range(total_players + 1):
        game["turn_index"] += 1
        if game["turn_index"] >= total_players:
            game["turn_index"] = 0
            game["round_number"] += 1

        next_id = order[game["turn_index"]]
        participant = next((p for p in game["participants"] if p["player_id"] == next_id), None)
        controlled = sum(1 for t in game["territories"] if t["owner_id"] == next_id)

        if controlled > 0 and not participant["eliminated"]:
            game["current_turn_player_id"] = next_id
            game["attack_used_this_turn"] = False
            game["active_attack"] = None
            # Rule: From the second round onward, at the start of each turn, receive 2 new soldiers per country controlled
            if game["round_number"] >= 2:
                game["pending_reinforcements"] = controlled * 2
            else:
                game["pending_reinforcements"] = 0
            return


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)