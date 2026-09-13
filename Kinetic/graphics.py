# graphics.py
import pygame
import os
import time
from config import *

class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("Arial", 30)
        self.title_font = pygame.font.SysFont("Arial", 60, bold=True)
        self.debug_font = pygame.font.SysFont("Consolas", 14, bold=True) 
        self.rules_h1 = pygame.font.SysFont("Arial", 28, bold=True)
        self.rules_h2 = pygame.font.SysFont("Arial", 22, bold=True)
        self.rules_p = pygame.font.SysFont("Arial", 18)
        
        self.BaseCardW, self.BaseCardH = 100, 135
        self.BaseGap = 25
        self.BaseDeckGap = 60
        
        self.CardW, self.CardH = 100, 135
        self.Gap = 25
        self.BoardWidth = 0
        self.BoardStartX = 0
        self.DeckP1_Pos = (0, 0)
        self.DeckP2_Pos = (0, 0)
        self.pile_rects = []
        
        self.card_images = {}
        self.card_back_image = None

        self.rules_text = [
            ("# KINETIC - MASTER RULESET", "h1"),
            ("", "p"),
            ("## 1. SETUP", "h2"),
            ("- Deck: Standard 52-card deck.", "p"),
            ("- Distribution: Shuffled and split evenly (26 cards per player).", "p"),
            ("- Hands: Players hold their decks face-down. They do not look at their cards.", "p"),
            ("- The Board: Both players simultaneously deal 4 cards face-up in front of them,", "p"),
            ("  forming a shared 8-pile grid (2x4).", "p"),
            ("", "p"),
            ("## 2. THE CORE LOOP", "h2"),
            ("- The Scan: Players continuously scan the 8 visible top cards for rank matches", "p"),
            ("  (e.g., two 4s, three Jacks). Suits are ignored.", "p"),
            ("- Valid Targets: Any matching cards independently become valid targets.", "p"),
            ("- The Play: Players race to take the top card from their face-down deck and", "p"),
            ("  blindly flip it onto a valid target pile as fast as possible.", "p"),
            ("- Target Closing: Flipping a card onto a valid target 'closes' that specific pile.", "p"),
            ("  If there was a pair, the other card remains a valid target until a card is", "p"),
            ("  flipped onto it.", "p"),
            ("", "p"),
            ("## 3. THE STACKING LOOP", "h2"),
            ("- If a player flips a card onto a valid pile, and by pure luck it is the exact", "p"),
            ("  same rank as the card it just covered (e.g., flipping a 7 onto a 7), that", "p"),
            ("  pile instantly becomes an open target again. The player can immediately", "p"),
            ("  flip another card onto it.", "p"),
            ("", "p"),
            ("## 4. THE SCOOP (STUCK BOARD)", "h2"),
            ("- Condition: If there are zero rank matches among the 8 visible top cards, the", "p"),
            ("  board is deadlocked.", "p"),
            ("- Action: Both players scoop their respective 4 piles, place them at the bottom", "p"),
            ("  of their face-down deck, and redeal 4 new cards face-up to restart the loop.", "p"),
            ("", "p"),
            ("## 5. WIN CONDITION", "h2"),
            ("- The first player to completely empty their face-down deck wins the game.", "p")
        ]
        
    def _load_image_clean(self, path, target_w, target_h):
        try:
            img = pygame.image.load(path).convert_alpha()
            scaled_img = pygame.transform.smoothscale(img, (target_w, target_h))
            radius = max(2, int(target_w * 0.05))
            pygame.draw.rect(scaled_img, (0, 0, 0, 150), (0, 0, target_w, target_h), 1, border_radius=radius)
            return scaled_img
        except Exception as e:
            return None

    def load_assets(self):
        self.card_images = {}
        base_dir = "PNG_cards"
        
        if not os.path.exists(base_dir): return
            
        suits = ['C', 'D', 'H', 'S']
        ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
        
        for r in ranks:
            for s in suits:
                fname = f"{r}{s}.png"
                path = os.path.join(base_dir, fname)
                if os.path.exists(path):
                    img = self._load_image_clean(path, self.CardW, self.CardH)
                    if img: self.card_images[f"{r}_of_{s}"] = img

        found_back = False
        for back_name in ["1B.png", "2B.png"]:
            path = os.path.join(base_dir, back_name)
            if os.path.exists(path):
                img = self._load_image_clean(path, self.CardW, self.CardH)
                if img:
                    self.card_back_image = img
                    found_back = True
                    break
                    
        if not found_back:
            s = pygame.Surface((self.CardW, self.CardH))
            s.fill((60, 80, 150))
            pygame.draw.rect(s, (200,200,200), (5,5,self.CardW-10, self.CardH-10), 2)
            pygame.draw.rect(s, (0,0,0,150), (0,0,self.CardW,self.CardH), 1)
            self.card_back_image = s

    def calculate_layout(self, w, h):
        target_abstract_height = (3 * self.BaseCardH) + self.BaseGap + (2 * self.BaseDeckGap)
        scale = h / target_abstract_height
        
        self.CardW = int(self.BaseCardW * scale)
        self.CardH = int(self.BaseCardH * scale)
        self.Gap = int(self.BaseGap * scale)       
        scaled_deck_gap = int(self.BaseDeckGap * scale)   

        self.BoardWidth = (4 * self.CardW) + (3 * self.Gap)
        self.BoardStartX = (w - self.BoardWidth) // 2
        
        center_y = h // 2
        deck_x_centered = (w // 2) - (self.CardW // 2)
        
        cpu_y = (center_y - (self.Gap // 2) - self.CardH) - scaled_deck_gap - self.CardH
        self.DeckP2_Pos = (deck_x_centered, cpu_y)
        
        p1_y = (center_y + (self.Gap // 2) + self.CardH) + scaled_deck_gap
        self.DeckP1_Pos = (deck_x_centered, p1_y)
        
        self.pile_rects = []
        for i in range(8):
            r, col = i // 4, i % 4
            sx = self.BoardStartX + col * (self.CardW + self.Gap)
            sy = (center_y - self.CardH - (self.Gap // 2)) if r == 0 else (center_y + (self.Gap // 2))
            self.pile_rects.append(pygame.Rect(sx, sy, self.CardW, self.CardH))
            
        self.load_assets()

    def draw_neat_deck(self, count, x, y):
        if count <= 0:
            pygame.draw.rect(self.screen, (40, 40, 40), (x, y, self.CardW, self.CardH), border_radius=8)
            pygame.draw.rect(self.screen, (60, 60, 60), (x, y, self.CardW, self.CardH), 2, border_radius=8)
            return
        
        depth_px = min(25, int(count * 0.5))
        if self.card_back_image:
            for i in range(depth_px, 0, -1):
                 self.screen.blit(self.card_back_image, (x - i, y + i))
            self.screen.blit(self.card_back_image, (x, y))

    def draw_card(self, surface, card, rect, sync_now_ms, face_up=True, highlight_color=None):
        if not card: return

        draw_x = card.current_pos[0] if card.is_animating else rect.x + card.skew_offset[0]
        draw_y = card.current_pos[1] if card.is_animating else rect.y + card.skew_offset[1]
        angle = card.angle if card.is_animating else card.skew_angle
        scale_y = card.scale_y

        actual_face_up = card.face_up
        if card.is_animating and card.perform_flip:
            t = min(1.0, (sync_now_ms - card.anim_start_ms) / max(1, card.duration_ms))
            t = max(0.0, t)
            actual_face_up = card.face_up if t < 0.5 else not card.face_up
        elif not card.is_animating:
            actual_face_up = face_up

        if actual_face_up and card.name in self.card_images:
            base_surf = self.card_images[card.name]
        elif not actual_face_up and self.card_back_image:
            base_surf = self.card_back_image
        else:
            base_surf = pygame.Surface((self.CardW, self.CardH), pygame.SRCALPHA)
            color = CARD_BG if actual_face_up else CARD_BACK
            pygame.draw.rect(base_surf, color, base_surf.get_rect(), border_radius=5)
            pygame.draw.rect(base_surf, (0,0,0), base_surf.get_rect(), 2, border_radius=5)
            if actual_face_up:
                text = self.font.render(str(card.rank), True, ERROR_COLOR if card.suit in ['H','D'] else (0,0,0))
                base_surf.blit(text, (5, 5))

        if highlight_color:
            card_surface = base_surf.copy()
            pygame.draw.rect(card_surface, highlight_color, card_surface.get_rect(), 4, border_radius=5)
        else:
            card_surface = base_surf

        if scale_y != 1.0 and card_surface:
            cw, ch = card_surface.get_size()
            new_h = max(1, int(ch * scale_y))
            card_surface = pygame.transform.smoothscale(card_surface, (cw, new_h))

        if angle != 0 and card_surface:
            card_surface = pygame.transform.rotozoom(card_surface, angle, 1.0)
            new_rect = card_surface.get_rect(center=(draw_x + self.CardW//2, draw_y + self.CardH//2))
            surface.blit(card_surface, new_rect.topleft)
        else:
            surface.blit(card_surface, (draw_x, draw_y))

    def draw_debug_overlay(self, engine, bot, game_mode, local_p_id=1, remote_p_id=2, sync_now_ms=0):
        overlay_surf = pygame.Surface((300, 350), pygame.SRCALPHA)
        overlay_surf.fill((0, 0, 0, 180)) 
        self.screen.blit(overlay_surf, (10, 100))
        
        curr_t = int(time.time() * 1000)
        
        lines = [
            "--- DEBUG INFO ---", 
            f"Match Rating: {engine.get_rating()}"
        ]
        
        if game_mode == MODE_BOT:
            p1_f = len([c for c in engine.bumps[1]])
            p2_f = len([c for c in engine.bumps[2]])
            lines.extend([
                "YOU (P1)",
                f"  Bumps: {p1_f}",
                "CPU/P2",
                f"  Bumps: {p2_f}"
            ])
            if bot:
                countdown = max(0, bot.next_action_time - sync_now_ms)
                lines.extend([
                    f"  Target: {bot.target_pile if bot.target_pile is not None else 'None'}",
                    f"  State: {bot.state}",
                    f"  Timer: {countdown}ms",
                    f"  Rating: {getattr(bot, 'rating', 'N/A')}",
                    f"  P2 Penalty: {max(0, engine.penalties[2] - curr_t)}ms"
                ])
        elif game_mode == MODE_SINGLE:
            pen_time = max(0, engine.penalties[1] - curr_t)
            lines.extend([
                "MODE: Practice Solo",
                "BOARD STATE",
                f"  Valid Targets: {len(engine.valid_targets)}",
                f"  Verified Stuck: {engine.verify_board_stuck()}",
                f"P1 Penalty: {pen_time}ms"
            ])
        elif game_mode == MODE_LAN:
            loc_f = len([c for c in engine.bumps[local_p_id]])
            rem_f = len([c for c in engine.bumps[remote_p_id]])
            lines.extend([
                "MODE: Multiplayer (Local)",
                f"YOU (P{local_p_id})",
                f"  Bumps: {loc_f}",
                f"OPPONENT (P{remote_p_id})",
                f"  Bumps: {rem_f}"
            ])

        for i, line in enumerate(lines):
            col = (100, 200, 255) if "SCANNING" in line else ((100, 255, 100) if "CHAINING" in line else (255, 255, 255))
            self.screen.blit(self.debug_font.render(line, True, col), (20, 110 + i * 22))

    def draw_vision_overlay(self, engine, bot, game_mode):
        engine_valid = engine.valid_targets
        
        for i in range(8):
            rect = self.pile_rects[i]
            hitbox = rect.inflate(self.Gap, self.Gap)
            color = None
            if game_mode == MODE_BOT and bot and i == bot.target_pile: 
                color = (0, 0, 255, 100) 
            elif i in engine_valid: 
                color = (0, 255, 0, 100)
            
            if color:
                s = pygame.Surface((hitbox.w, hitbox.h), pygame.SRCALPHA)
                s.fill(color)
                self.screen.blit(s, (hitbox.x, hitbox.y))

            if engine.piles[i]:
                top_card = engine.piles[i][-1]
                label_str = f"{top_card.rank}-{top_card.suit}"
                label = self.debug_font.render(label_str, True, (255, 255, 0))
                shadow = self.debug_font.render(label_str, True, (0, 0, 0))
                self.screen.blit(shadow, (rect.x + 2, rect.y + 2))
                self.screen.blit(label, (rect.x, rect.y))

    def render_menu(self, buttons):
        self.screen.fill(BG_COLOR)
        title_surf = self.title_font.render("Kinetic", True, TEXT_COLOR)
        title_rect = title_surf.get_rect(center=(self.screen.get_width() // 2, 100))
        self.screen.blit(title_surf, title_rect)
        for btn in buttons:
            btn.draw(self.screen, self.font)

    def render_bot_select(self, slider, minus_btn, plus_btn, start_btn, back_btn, input_active=False, input_text=""):
        self.screen.fill(BG_COLOR)
        t_surf = self.title_font.render("Select Opponent Rating", True, TEXT_COLOR)
        self.screen.blit(t_surf, t_surf.get_rect(center=(self.screen.get_width()//2, 100)))
        
        display_str = input_text + "|" if input_active else str(slider.val)
        val_surf = self.title_font.render(display_str, True, (150, 200, 255))
        val_rect = val_surf.get_rect(center=(self.screen.get_width()//2, slider.rect.y - 50))
        self.screen.blit(val_surf, val_rect)
        
        slider.draw(self.screen, self.font)
        minus_btn.draw(self.screen, self.font)
        plus_btn.draw(self.screen, self.font)
        start_btn.draw(self.screen, self.font)
        back_btn.draw(self.screen, self.font)

        return val_rect

    def render_mp_ui(self, state, buttons, text_input=None, player_name="", opponent_name="",
                     peer_list=None, lan_timed_out=False, lan_status_text="", show_debug=False):
        self.screen.fill(BG_COLOR)
        
        title = "Multiplayer"
        msg = ""
        sub_msg = ""
        
        if state == STATE_MP_MODE_SELECT:
            title = "Multiplayer"
            msg = f"Playing as: {player_name}"
        elif state == STATE_ONLINE_WIP:
            title = "Online Play"
            msg = "Work in progress — not available yet."
        elif state == STATE_LAN_CONNECTING:
            title = "Local Network"
            msg = f"Playing as {player_name}"
            sub_msg = "No one found nearby — try again" if lan_timed_out else lan_status_text
        elif state == STATE_LAN_PEER_PICKER:
            title = "Multiple players found"
            msg = "Tap one to connect:"
        elif state == STATE_MATCH_STARTING:
            title = "MATCH STARTING!"
            msg = f"{player_name} vs {opponent_name}" if opponent_name else "Get Ready..."
            
        t_surf = self.title_font.render(title, True, TEXT_COLOR)
        self.screen.blit(t_surf, t_surf.get_rect(center=(self.screen.get_width()//2, 100)))
        
        if msg:
            m_surf = self.rules_h2.render(msg, True, (200, 200, 255))
            self.screen.blit(m_surf, m_surf.get_rect(center=(self.screen.get_width()//2, 180)))
        if sub_msg:
            sm_surf = self.rules_p.render(sub_msg, True, (200, 200, 200))
            self.screen.blit(sm_surf, sm_surf.get_rect(center=(self.screen.get_width()//2, 220)))
            
        if text_input:
            text_input.draw(self.screen, self.font)

        for btn in buttons:
            if "DEBUG" in btn.text and not show_debug:
                continue
            btn.draw(self.screen, self.font)

    def render_help(self, back_button):
        self.screen.fill(BG_COLOR)
        
        start_x = self.screen.get_width() // 2 - 400
        start_y = 50
        
        for text, style in self.rules_text:
            if style == "h1":
                surf = self.rules_h1.render(text, True, (255, 200, 100))
                self.screen.blit(surf, (self.screen.get_width() // 2 - surf.get_width() // 2, start_y))
                start_y += 40
            elif style == "h2":
                surf = self.rules_h2.render(text, True, (150, 200, 255))
                self.screen.blit(surf, (start_x, start_y))
                start_y += 30
            else:
                if text == "":
                    start_y += 10
                else:
                    surf = self.rules_p.render(text, True, TEXT_COLOR)
                    self.screen.blit(surf, (start_x + 10, start_y))
                    start_y += 24
                    
        back_button.draw(self.screen, self.font)

    def render_game_over(self, winner_text, buttons):
        overlay = pygame.Surface((self.screen.get_width(), self.screen.get_height()), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))
        
        text_color = (100, 255, 100) if "YOU" in winner_text.upper() else (255, 100, 100)
        title_surf = self.title_font.render(winner_text, True, text_color)
        title_rect = title_surf.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 100))
        self.screen.blit(title_surf, title_rect)
        
        for btn in buttons:
            btn.draw(self.screen, self.font)

    def render_game(self, engine, bot, game_mode, show_debug, sync_now_ms, local_p_id=1, remote_p_id=2, opponent_name="", dev_btns=None):
        self.screen.fill(BG_COLOR)
        
        under_deck_animating = []
        over_deck_animating = []

        # 1. Draw Piles (Static cards only)
        for i, pile in enumerate(engine.piles):
            rect = self.pile_rects[i]
            pygame.draw.rect(self.screen, (50, 50, 50), rect, 2, border_radius=8) 
            for card in pile: 
                card.update(sync_now_ms)
                if card.is_animating:
                    over_deck_animating.append((card, rect, True, None))
                else:
                    self.draw_card(self.screen, card, rect, sync_now_ms, face_up=True)

        # 2. Collect Penalty Cards from Decks
        if engine.decks[local_p_id].cards:
            top_p1 = engine.decks[local_p_id].cards[0]
            top_p1.update(sync_now_ms)
            if top_p1.is_animating:
                over_deck_animating.append((top_p1, pygame.Rect(*self.DeckP1_Pos, self.CardW, self.CardH), False, None))
                
        if engine.decks[remote_p_id].cards:
            top_p2 = engine.decks[remote_p_id].cards[0]
            top_p2.update(sync_now_ms)
            if top_p2.is_animating:
                over_deck_animating.append((top_p2, pygame.Rect(*self.DeckP2_Pos, self.CardW, self.CardH), False, None))

        # 3. Collect Bumped Cards
        for p_id in [1, 2]:
            for card in engine.bumps[p_id]:
                card.update(sync_now_ms)
                c_rect = pygame.Rect(
                    int(card.current_pos[0] - card.skew_offset[0]), 
                    int(card.current_pos[1] - card.skew_offset[1]), 
                    self.CardW, self.CardH
                )
                h_color = None
                if card.is_hovered and not card.is_returning:
                    h_color = (50, 255, 50) if p_id == local_p_id else (255, 50, 50)
                
                if card.is_returning:
                    under_deck_animating.append((card, c_rect, card.face_up, h_color))
                else:
                    over_deck_animating.append((card, c_rect, card.face_up, h_color))

        # 4. Draw returning bumped cards (UNDER the decks)
        for card, rect, face_up, h_color in under_deck_animating:
            self.draw_card(self.screen, card, rect, sync_now_ms, face_up=face_up, highlight_color=h_color)

        # 5. Draw Neat Decks
        self.draw_neat_deck(len(engine.decks[local_p_id].cards), self.DeckP1_Pos[0], self.DeckP1_Pos[1])
        self.screen.blit(self.font.render(f"YOU: {len(engine.decks[local_p_id].cards)}", True, (200,200,200)), (self.DeckP1_Pos[0] + self.CardW + 20, self.DeckP1_Pos[1] + 10))

        opp_label = opponent_name if opponent_name else "CPU/OPP"
        self.draw_neat_deck(len(engine.decks[remote_p_id].cards), self.DeckP2_Pos[0], self.DeckP2_Pos[1])
        self.screen.blit(self.font.render(f"{opp_label}: {len(engine.decks[remote_p_id].cards)}", True, (200,200,200)), (self.DeckP2_Pos[0] + self.CardW + 20, self.DeckP2_Pos[1] + self.CardH - 55))

        # 6. Draw all other animating cards ON TOP
        for card, rect, face_up, h_color in over_deck_animating:
            self.draw_card(self.screen, card, rect, sync_now_ms, face_up=face_up, highlight_color=h_color)

        # Debug Overlays & Dev Panel
        if show_debug:
            self.draw_vision_overlay(engine, bot, game_mode)
            self.draw_debug_overlay(engine, bot, game_mode, local_p_id, remote_p_id, sync_now_ms)
            
            # Draw Developer Panel (Top Right)
            panel_w = 200
            panel_h = 300
            panel_x = self.screen.get_width() - panel_w - 20
            panel_y = 100
            
            overlay_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            overlay_surf.fill((0, 0, 0, 180))
            self.screen.blit(overlay_surf, (panel_x, panel_y))
            
            title = self.debug_font.render("--- DEV PANEL ---", True, (255, 200, 100))
            self.screen.blit(title, (panel_x + 10, panel_y + 10))
            
            if dev_btns:
                for btn in dev_btns:
                    btn.draw(self.screen, self.font)

        self.screen.blit(pygame.font.SysFont("Arial", 24).render("ESC: Menu", True, (150,150,150)), (10,10))