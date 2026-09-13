# bot.py
"""
Bot logic and AI state machine.
"""
import random

class Bot:
    def __init__(self, player_id=2, rating=300):
        self.p_id = player_id
        self.rating = rating
        self.state = "SCANNING"
        self.target_pile = None
        
        # State Machine Memory
        self.next_action_time = 0
        self.move_queue = []
        
        # Hardcoded for debugging
        self.scan_base = 3000
        self.chain_base = 1000
        
        # Micro-memory to prevent phantom stutter
        self.ignored_piles = {}

    def _group_valid_targets(self, engine, sync_now_ms):
        """
        Exclusively looks at engine.valid_targets.
        Ignores piles that were recently hit to allow the engine buffer to resolve.
        Groups them by rank so the bot can chain multiples.
        """
        rank_map = {}
        for i in engine.valid_targets:
            # Skip if this pile is on the ignore list
            if i in self.ignored_piles and sync_now_ms < self.ignored_piles[i]:
                continue
                
            pile = engine.piles[i]
            if pile:
                rank = pile[-1].rank
                if rank not in rank_map:
                    rank_map[rank] = []
                rank_map[rank].append(i)

        moves = list(rank_map.values())
        random.shuffle(moves)
        return moves

    def _fmt_time(self, current_ms, start_ms):
        elapsed = max(0, current_ms - start_ms)
        s = elapsed / 1000.0
        m = int(s // 60)
        sec = s % 60
        return f"[T+{m}:{sec:06.3f}]"

    def update(self, engine, sync_now_ms, sf=1, auto_stuck=False, opportunistic=False, social_pressure=False, match_start_time=0):
        """
        Processes the bot's state machine. 
        Returns an intent dict if a play is executed this tick, otherwise None.
        """
        # Clean up old ignore list entries
        for p in list(self.ignored_piles.keys()):
            if sync_now_ms >= self.ignored_piles[p]:
                del self.ignored_piles[p]

        if self.state == "SCANNING":
            if not self.move_queue:
                moves = self._group_valid_targets(engine, sync_now_ms)
                
                if moves:
                    self.move_queue = moves[0] # Load the first matched packet
                    delay = int(self.scan_base * sf)
                    self.next_action_time = sync_now_ms + delay
                    self.target_pile = self.move_queue[0]
                    print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Target Locked: {self.move_queue}. Scanning for {delay}ms.")
                else:
                    self.target_pile = None
                    return None
                        
            if self.move_queue:
                intended_pile = self.move_queue[0]
                
                # Continually verify the target is structurally valid while the scan timer ticks down
                if intended_pile not in engine.valid_targets:
                    print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Target {intended_pile} invalidated during SCAN. Dropping packet.")
                    self.move_queue.clear()
                    self.target_pile = None
                    return None
                    
                # The timer hits 0: Fire play intent and transition
                if sync_now_ms >= self.next_action_time:
                    hit_target = self.move_queue.pop(0)
                    print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] FIRE! Hitting pile {hit_target}.")
                    
                    # Add to ignore list for 100ms
                    self.ignored_piles[hit_target] = sync_now_ms + 100
                    
                    if self.move_queue:
                        self.state = "CHAINING"
                        delay = int(self.chain_base * sf)
                        self.next_action_time = sync_now_ms + delay
                        self.target_pile = self.move_queue[0]
                        print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] State -> CHAINING. Next target {self.target_pile} in {delay}ms.")
                    else:
                        self.state = "SCANNING"
                        self.target_pile = None
                        print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Packet complete. State -> SCANNING.")
                        
                    return {"type": "play", "p_id": self.p_id, "pile": hit_target}
            
            return None
            
        elif self.state == "CHAINING":
            if not self.move_queue:
                self.state = "SCANNING"
                self.target_pile = None
                return None

            intended_pile = self.move_queue[0]
            
            # The Micro-Check: Verify the intended pile is still structurally valid while chaining
            if intended_pile not in engine.valid_targets:
                print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Target {intended_pile} invalidated during CHAIN. Dropping packet. State -> SCANNING.")
                self.move_queue.clear()
                self.state = "SCANNING"
                self.target_pile = None
                return None
                
            # The timer hits 0: Fire play intent
            if sync_now_ms >= self.next_action_time:
                hit_target = self.move_queue.pop(0)
                print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] CHAIN FIRE! Hitting pile {hit_target}.")
                
                # Add to ignore list for 100ms
                self.ignored_piles[hit_target] = sync_now_ms + 100
                
                if self.move_queue:
                    delay = int(self.chain_base * sf)
                    self.next_action_time = sync_now_ms + delay
                    self.target_pile = self.move_queue[0]
                    print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Looping CHAINING. Next target {self.target_pile} in {delay}ms.")
                else:
                    self.state = "SCANNING"
                    self.target_pile = None
                    print(f"{self._fmt_time(sync_now_ms, match_start_time)} [BOT] Packet complete. State -> SCANNING.")
                    
                return {"type": "play", "p_id": self.p_id, "pile": hit_target}

        return None