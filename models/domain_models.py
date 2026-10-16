import math
import random
from abc import ABC, abstractmethod


class PopulationCalculator:
    """Maps Worldometer population counts to starting soldiers (Case Study Table)."""

    @staticmethod
    def calculate_soldiers(population: int) -> int:
        if population <= 5_000_000:
            return 1
        elif population <= 10_000_000:
            return 2
        elif population <= 25_000_000:
            return 3
        elif population <= 50_000_000:
            return 4
        elif population <= 75_000_000:
            return 5
        elif population <= 100_000_000:
            return 6
        elif population <= 125_000_000:
            return 7
        elif population <= 150_000_000:
            return 8
        else:
            return 9


class CountryTerritory:
    """Encapsulated representation of a Nation on the board."""

    def __init__(self, name: str, population: int, owner_id: str, soldiers: int = None, base_value: int = None):
        self._name = name
        self._population = int(population)
        self._base_value = base_value if base_value is not None else PopulationCalculator.calculate_soldiers(self._population)
        self._soldiers = soldiers if soldiers is not None else self._base_value
        self._owner_id = owner_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def population(self) -> int:
        return self._population

    @property
    def base_value(self) -> int:
        return self._base_value

    @property
    def soldiers(self) -> int:
        return self._soldiers

    @soldiers.setter
    def soldiers(self, value: int):
        if value < 0:
            raise ValueError("Soldier count cannot be negative.")
        self._soldiers = int(value)

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @owner_id.setter
    def owner_id(self, new_owner: str):
        if not new_owner:
            raise ValueError("Country must have a valid owner_id.")
        self._owner_id = new_owner

    def conquest_reward(self) -> int:
        """Rule: Soldiers gained = Max(2, floor(conquered country's soldier value / 2))."""
        return max(2, self._base_value // 2)

    def can_attack(self) -> bool:
        """Rule: Need at least 2 soldiers to attack or continue attacking."""
        return self._soldiers >= 2

    def max_attacking_dice(self) -> int:
        """Rule: Must leave at least 1 soldier behind in the attacking country."""
        return max(0, self._soldiers - 1)

    def to_dict(self) -> dict:
        return {
            "name": self._name,
            "population": self._population,
            "base_value": self._base_value,
            "soldiers": self._soldiers,
            "owner_id": self._owner_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CountryTerritory":
        return cls(
            name=data["name"],
            population=data["population"],
            owner_id=data["owner_id"],
            soldiers=data["soldiers"],
            base_value=data["base_value"]
        )


class Participant(ABC):
    """Abstract base class for Human and NPC commanders."""

    def __init__(self, player_id: str, display_name: str, home_country: str, is_npc: bool, eliminated: bool = False):
        self._player_id = player_id
        self._display_name = display_name
        self._home_country = home_country
        self._is_npc = is_npc
        self._eliminated = eliminated

    @property
    def player_id(self) -> str:
        return self._player_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def is_npc(self) -> bool:
        return self._is_npc

    @property
    def eliminated(self) -> bool:
        return self._eliminated

    @eliminated.setter
    def eliminated(self, status: bool):
        self._eliminated = bool(status)

    def calculate_reinforcements(self, controlled_count: int, round_number: int) -> int:
        """Rule: From Round 2 onward, receive 2 new soldiers for every country controlled."""
        if round_number < 2 or self._eliminated or controlled_count == 0:
            return 0
        return controlled_count * 2

    @abstractmethod
    def to_dict(self) -> dict:
        pass


class HumanPlayer(Participant):
    def __init__(self, player_id: str, display_name: str, home_country: str, eliminated: bool = False):
        super().__init__(player_id, display_name, home_country, is_npc=False, eliminated=eliminated)

    def to_dict(self) -> dict:
        return {
            "player_id": self._player_id,
            "display_name": self._display_name,
            "home_country": self._home_country,
            "is_npc": False,
            "eliminated": self._eliminated,
            "personality": "Human Strategist"
        }


class NPCPlayer(Participant):
    """Intelligent NPC that evaluates board utility and outputs decision justifications."""

    def __init__(self, player_id: str, display_name: str, home_country: str, personality: str = "Calculated Expansionist", eliminated: bool = False):
        super().__init__(player_id, display_name, home_country, is_npc=True, eliminated=eliminated)
        self._personality = personality

    def allocate_reinforcements(self, my_countries: list[CountryTerritory], all_countries: list[CountryTerritory], pool: int) -> tuple[dict, str]:
        """Distributes reinforcements to the strongest launchpad or most vulnerable border."""
        if not my_countries or pool <= 0:
            return {}, "No reinforcements available this round."

        # Identify highest-soldier territory to create a decisive strike force
        strike_base = max(my_countries, key=lambda c: c.soldiers)
        strike_base.soldiers += pool
        justification = (
            f"[{self._personality}] Allocated +{pool} reinforcement soldiers to {strike_base.name} "
            f"(bringing garrison to {strike_base.soldiers}) to build a decisive offensive spearhead."
        )
        return {strike_base.name: pool}, justification

    def decide_transfer(self, my_countries: list[CountryTerritory]) -> tuple[dict | None, str]:
        """Consolidates rear-guard troops into the primary attacking nation while leaving at least 1 soldier behind."""
        if len(my_countries) < 2:
            return None, "Single territory controlled; tactical troop transfer skipped."

        sorted_by_strength = sorted(my_countries, key=lambda c: c.soldiers, reverse=True)
        lead_nation = sorted_by_strength[0]
        donor_nation = sorted_by_strength[-1]

        if donor_nation.soldiers > 2:
            transfer_amt = donor_nation.soldiers - 1  # Leave 1 soldier behind per rule
            donor_nation.soldiers -= transfer_amt
            lead_nation.soldiers += transfer_amt
            return (
                {"from": donor_nation.name, "to": lead_nation.name, "amount": transfer_amt},
                f"Transferred {transfer_amt} soldiers from {donor_nation.name} to {lead_nation.name} "
                f"(retaining 1 garrison soldier in {donor_nation.name}) to maximize attack dice."
            )
        return None, "All controlled territories are at minimum garrison thresholds; no transfer executed."

    def choose_attack_target(self, my_countries: list[CountryTerritory], enemy_countries: list[CountryTerritory]) -> tuple[CountryTerritory | None, CountryTerritory | None, str]:
        """Evaluates force-ratio utility and conquest reward to play to win."""
        capable_attackers = [c for c in my_countries if c.can_attack()]
        if not capable_attackers or not enemy_countries:
            return None, None, "Insufficient soldiers (minimum 2 required) to launch an offensive. Skipping attack."

        best_attacker = max(capable_attackers, key=lambda c: c.soldiers)
        # Score targets by highest ratio of (Attacker Soldiers - 1) / Defender Soldiers, breaking ties by highest conquest reward
        scored_targets = []
        for enemy in enemy_countries:
            force_ratio = (best_attacker.soldiers - 1) / max(1, enemy.soldiers)
            reward = enemy.conquest_reward()
            utility_score = (force_ratio * 2.5) + (reward * 0.4)
            scored_targets.append((utility_score, force_ratio, reward, enemy))

        scored_targets.sort(key=lambda x: x[0], reverse=True)
        best_score, best_ratio, best_reward, target = scored_targets[0]

        # Play to win: only attack if force ratio is favorable (>= 1.0) or attacker has overwhelming reserve (>= 5)
        if best_ratio >= 1.0 or best_attacker.soldiers >= 5:
            reason = (
                f"Targeted {target.name} ({target.soldiers} soldiers) from {best_attacker.name} ({best_attacker.soldiers} soldiers). "
                f"Force advantage ratio is {best_ratio:.2f}:1 with a potential conquest yield of +{best_reward} bonus soldiers."
            )
            return best_attacker, target, reason

        return (
            None,
            None,
            f"Held position: Strongest garrison {best_attacker.name} ({best_attacker.soldiers} soldiers) faces unfavorable odds "
            f"against weakest rival {target.name} ({target.soldiers} soldiers, ratio {best_ratio:.2f}:1). Preserving troops for next round."
        )

    def should_continue_attack(self, attacker: CountryTerritory, defender: CountryTerritory) -> tuple[bool, str]:
        """Determines whether to press the attack or call off the offensive mid-battle."""
        if not attacker.can_attack():
            return False, f"Offensive halted automatically: {attacker.name} is down to 1 remaining soldier."
        ratio = (attacker.soldiers - 1) / max(1, defender.soldiers)
        if ratio >= 0.75 or defender.soldiers == 1:
            return True, f"Pressing assault: {attacker.name} ({attacker.soldiers} troops) maintains pressure on {defender.name} ({defender.soldiers} troops)."
        return False, f"Tactical withdrawal: {attacker.name} halted the assault with {attacker.soldiers} soldiers to avoid over-extension against {defender.name} ({defender.soldiers} soldiers)."

    def to_dict(self) -> dict:
        return {
            "player_id": self._player_id,
            "display_name": self._display_name,
            "home_country": self._home_country,
            "is_npc": True,
            "eliminated": self._eliminated,
            "personality": self._personality
        }


class BattleEngine:
    """Executes exact dice-pairing rules from the Geopolitics Case Study."""

    @staticmethod
    def execute_dice_phase(attacker: CountryTerritory, defender: CountryTerritory) -> dict:
        if not attacker.can_attack():
            raise ValueError(f"{attacker.name} requires at least 2 soldiers to attack.")

        # Rule: Number of dice rolled is determined by the least number of soldiers available to fight on either side.
        # Attacker must always leave 1 soldier behind (attacker.soldiers - 1).
        num_dice = min(attacker.max_attacking_dice(), defender.soldiers)

        attacker_rolls = [random.randint(1, 6) for _ in range(num_dice)]
        defender_rolls = [random.randint(1, 6) for _ in range(num_dice)]

        attacker_losses = 0
        defender_losses = 0
        pairings = []

        # Rule: Each attacking die is paired with a defending die: Soldier 1 vs Soldier 1, Soldier 2 vs Soldier 2.
        # Higher roll wins; tie = no soldier dies.
        for idx in range(num_dice):
            a_die = attacker_rolls[idx]
            d_die = defender_rolls[idx]
            if a_die > d_die:
                defender_losses += 1
                outcome = "ATTACKER_WIN"
            elif d_die > a_die:
                attacker_losses += 1
                outcome = "DEFENDER_WIN"
            else:
                outcome = "TIE_NO_LOSS"

            pairings.append({
                "soldier_pair": idx + 1,
                "attacker_die": a_die,
                "defender_die": d_die,
                "outcome": outcome
            })

        attacker.soldiers -= attacker_losses
        defender.soldiers -= defender_losses

        conquered = defender.soldiers == 0
        bonus_gained = 0
        auto_transferred = 0

        if conquered:
            # Rule: Gained = Max(2, floor(conquered country's soldier value / 2))
            bonus_gained = defender.conquest_reward()
            defender.owner_id = attacker.owner_id
            # Move at least 1 occupying soldier from attacker (if >1) + bonus soldiers to conquered nation
            if attacker.soldiers > 1:
                auto_transferred = 1
                attacker.soldiers -= 1
            defender.soldiers = bonus_gained + auto_transferred

        return {
            "attacker_country": attacker.name,
            "defender_country": defender.name,
            "num_dice": num_dice,
            "pairings": pairings,
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "attacker_remaining": attacker.soldiers,
            "defender_remaining": defender.soldiers,
            "conquered": conquered,
            "bonus_soldiers_gained": bonus_gained,
            "attacker_forced_stop": attacker.soldiers == 1 and not conquered
        }