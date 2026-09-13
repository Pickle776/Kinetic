# engine.py
import time
from game_objects import Card, Deck

class SequenceScheduler:
    def __init__(self):
        self.pending_sequence = None
        self.target_time_ms = None
        self.args = {}

    def schedule(self, sequence_name, target_time_ms, **kwargs):
        self.pending_sequence = sequence_name
        self.target_time_ms = target_time_ms
        self.args = kwargs

    def check(self, sync_now_ms):
        if self.pending_sequence and sync_now_ms >= self.target_time_ms:
            seq = self.pending_sequence
            args = self.args
            self.pending_sequence = None
            self.target_time_ms = None
            self.args = {}
            return seq, args
        return None, None
        
    def cancel(self):
        self.pending_sequence = None
        self.target_time_ms = None
        self.args = {}

class KineticEngine:
    def __init__(self):
        self.piles = [[] for _ in range(8)]
        self.decks = {1: Deck(), 2: Deck()}
        self.bumps = {1: [], 2: []}
        self.flashed_cards = {1: None, 2: None} 
        self.penalties = {1: 0, 2: 0}
        self.stuck_calls = {1: None, 2: None}
        self.last_pile_times = [0] * 8
        self.match_history_ms = []
        
        self.valid_targets = set()

    def setup_game(self, full_deck_cards):
        self.piles = [[] for _ in range(8)]
        self.bumps = {1: [], 2: []}
        self.flashed_cards = {1: None, 2: None}
        self.stuck_calls = {1: None, 2: None}
        self.valid_targets.clear()
        self.last_pile_times = [0] * 8
        
        half = len(full_deck_cards) // 2
        self.decks[1] = Deck(full_deck_cards[:half])
        self.decks[2] = Deck(full_deck_cards[half:])
        
    def update_valid_targets(self):
        tops = [p[-1] if p else None for p in self.piles]
        ranks = {}
        
        for i, card in enumerate(tops):
            if card:
                ranks.setdefault(card.rank, []).append(i)
                
        for r, indices in ranks.items():
            if len(indices) >= 2:
                for idx in indices:
                    self.valid_targets.add(idx)
                    
        for i, pile in enumerate(self.piles):
            if len(pile) >= 2:
                if pile[-1].rank == pile[-2].rank:
                    self.valid_targets.add(i)

    def verify_board_stuck(self):
        ranks_visible = {}
        for pile in self.piles:
            if pile:
                r = pile[-1].rank
                ranks_visible[r] = ranks_visible.get(r, 0) + 1
        return not any(count >= 2 for count in ranks_visible.values())

    def attempt_play(self, player_id, pile_index, current_time):
        if self.penalties[player_id] > current_time:
            return False, "penalized"
            
        if self.decks[player_id].is_empty():
            return False, "empty_deck"

        top_card = self.decks[player_id].cards[0] 

        time_since_last_play = current_time - self.last_pile_times[pile_index]
        from config import CLASH_WINDOW, PENALTY_TIME
        if time_since_last_play < CLASH_WINDOW:
            bumped_card = self.decks[player_id].pop_top()
            self.bumps[player_id].append(bumped_card)
            return False, "bump"

        if pile_index in self.valid_targets:
            self.valid_targets.remove(pile_index) 
            played_card = self.decks[player_id].pop_top()
            self.piles[pile_index].append(played_card)
            self.last_pile_times[pile_index] = current_time
            self.flashed_cards[player_id] = None 
            self.stuck_calls = {1: None, 2: None} 
            return True, "success"
        else:
            self.penalties[player_id] = current_time + PENALTY_TIME 
            self.flashed_cards[player_id] = top_card 
            return False, "invalid"

    def execute_scoop_finish(self, scooped_p1, scooped_p2):
        self.decks[1].add_bottom(scooped_p1)
        self.decks[2].add_bottom(scooped_p2)
        
        self.decks[1].add_bottom(self.bumps[1])
        self.bumps[1].clear()
        self.decks[2].add_bottom(self.bumps[2])
        self.bumps[2].clear()
            
        self.stuck_calls = {1: None, 2: None}
        self.valid_targets.clear()

    def call_stuck(self, player_id, timestamp=None):
        self.stuck_calls[player_id] = timestamp if timestamp is not None else int(time.time() * 1000)

    def get_rating(self):
        if not self.match_history_ms: return 1000 
        avg_ms = sum(self.match_history_ms) / len(self.match_history_ms)
        return max(0, int(2000 - avg_ms))

    def get_ready_intents(self, pending_intents, current_sync_time, input_delay_ms):
        ready = []
        remaining = []
        for intent in pending_intents:
            if intent['timestamp'] <= current_sync_time - input_delay_ms:
                ready.append(intent)
            else:
                remaining.append(intent)
        
        ready.sort(key=lambda x: (x['timestamp'], x['p_id']))
        return ready, remaining