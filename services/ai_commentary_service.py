import os
import requests

class AICommentaryService:
    """Generates live LLM battle commentary as each dice roll phase unfolds."""

    @staticmethod
    def generate_battle_commentary(phase_result: dict, attacker_owner: str, defender_owner: str) -> str:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        pairs_summary = ", ".join(
            [f"Soldier {p['soldier_pair']}: [{p['attacker_die']} vs {p['defender_die']}]" for p in phase_result["pairings"]]
        )
        prompt = (
            f"Write a punchy 2-sentence geopolitical war-room broadcast for this Risk battle phase: "
            f"{phase_result['attacker_country']} ({attacker_owner}) attacked {phase_result['defender_country']} ({defender_owner}) "
            f"rolling {phase_result['num_dice']} dice ({pairs_summary}). "
            f"Attacker lost {phase_result['attacker_losses']} troops ({phase_result['attacker_remaining']} left); "
            f"Defender lost {phase_result['defender_losses']} troops ({phase_result['defender_remaining']} left). "
            f"Conquered: {phase_result['conquered']}."
        )

        if os.getenv("GEMINI_API_KEY"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={os.getenv('GEMINI_API_KEY')}"
                resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=3.5)
                if resp.status_code == 200:
                    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                pass

        # Instant high-immersion fallback if API key is unset or rate-limited
        if phase_result["conquered"]:
            return (
                f"⚡ BREAKING FROM FRONT: {phase_result['attacker_country']} shatters {phase_result['defender_country']}'s final defense line "
                f"({pairs_summary})! Territory annexed with +{phase_result['bonus_soldiers_gained']} conscripted reinforcement divisions!"
            )
        if phase_result["attacker_forced_stop"]:
            return (
                f"🛑 OFFENSIVE STALLED: Fierce resistance in {phase_result['defender_country']} ({pairs_summary}) leaves "
                f"{phase_result['attacker_country']} with just 1 surviving garrison division—assault terminated!"
            )
        return (
            f"🎲 FRONT-LINE CLASH ({pairs_summary}): {phase_result['attacker_country']} suffers {phase_result['attacker_losses']} casualties "
            f"({phase_result['attacker_remaining']} remaining) while inflicting {phase_result['defender_losses']} losses on "
            f"{phase_result['defender_country']} ({phase_result['defender_remaining']} remaining)."
        )