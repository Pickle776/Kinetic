# game_objects.py
import pygame
import random
import math
from config import BUTTON_COLOR, BUTTON_HOVER_COLOR, SCOOP_SPEED, FLIP_SPEED, NEAT_SPEED, PAUSE_DURATION, PENALTY_RETRACT_SPEED

def ease_in_out_cubic(t): return t * t * (3 - 2 * t)
def ease_linear(t): return t
def ease_out_quad(t): return t * (2 - t)

class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit
        self.name = f"{rank}_of_{suit}"
        
        # Physics State
        self.is_animating = False
        self.anim_start_ms = 0
        self.duration_ms = 250
        self.start_pos = (0, 0)
        self.target_pos = (0, 0)
        self.current_pos = (0, 0)
        self.start_angle = 0
        self.target_angle = 0
        self.perform_flip = False
        self.face_up = False
        self.easing_func = ease_in_out_cubic
        
        # Penalty / Bump States
        self.is_penalty = False
        self.penalty_phase = 0
        self.penalty_wait_until_ms = 0
        self.shake_until_ms = 0
        self.is_bumped = False
        self.pending_bounce_target = None
        
        # Interaction States
        self.is_hovered = False
        self.is_returning = False
        
        self.scale_y = 1.0 
        
        self.regenerate_layout()
        self.angle = self.final_angle

    def regenerate_layout(self):
        self.final_angle = random.uniform(-15, 15)
        self.final_offset_x = random.uniform(-4, 4)
        self.final_offset_y = random.uniform(-4, 4)
        self.skew_angle = self.final_angle
        self.skew_offset = (self.final_offset_x, self.final_offset_y)

    def make_neat(self): 
        self.final_angle = self.final_offset_x = self.final_offset_y = self.skew_angle = self.angle = 0
        self.skew_offset = (0, 0)

    def start_animation(self, start_xy, target_xy, sync_now_ms, duration_ms=250, flip=False, target_angle=None, easing=ease_in_out_cubic):
        self.angle = self.angle % 360
        if self.angle > 180: self.angle -= 360
        
        self.start_pos = start_xy
        self.target_pos = target_xy
        self.current_pos = start_xy
        self.start_angle = self.angle
        self.target_angle = target_angle if target_angle is not None else self.final_angle
        self.anim_start_ms = sync_now_ms
        self.duration_ms = duration_ms
        self.is_animating = True
        self.perform_flip = flip
        self.easing_func = easing
        self.is_penalty = False

    def trigger_penalty(self, start_xy, target_xy, sync_now_ms, sf=1): 
        self.start_animation(start_xy, target_xy, sync_now_ms, duration_ms=int(166*sf), flip=True)
        self.is_penalty = True
        self.penalty_phase = 0
        self.sf = sf

    def trigger_bump(self, start_pos, pile_target, skirt_target, sync_now_ms, sf=1):
        self.is_bumped = True
        self.start_animation(start_pos, pile_target, sync_now_ms, duration_ms=int(250*sf), flip=True)
        self.pending_bounce_target = skirt_target
        self.sf = sf

    def start_return_animation(self, dest_xy, sync_now_ms, sf=1):
        self.is_returning = True
        self.is_bumped = False
        self.pending_bounce_target = None
        self.start_animation(self.current_pos, dest_xy, sync_now_ms, duration_ms=int(333*sf), flip=True, target_angle=0)

    def _handle_penalty_logic(self, sync_now_ms):
        sf = getattr(self, 'sf', 1)
        if self.penalty_phase == 0: 
            wait_ms = int(300 * sf)
            self.penalty_phase = 1
            self.penalty_wait_until_ms = sync_now_ms + wait_ms
            self.shake_until_ms = sync_now_ms + wait_ms
            self.current_pos = self.target_pos
            self.face_up = True
            self.perform_flip = False
            return True 
        elif self.penalty_phase == 2: 
            self.is_animating, self.current_pos, self.is_penalty = False, self.target_pos, False
            self.angle = self.skew_angle = self.target_angle
            self.face_up = False
            return True
        return False

    def update(self, sync_now_ms):
        if self.is_penalty and self.penalty_phase == 1:
            if sync_now_ms >= self.penalty_wait_until_ms:
                self.penalty_phase, self.face_up = 2, True
                sf = getattr(self, 'sf', 1)
                self.start_animation(self.target_pos, self.start_pos, sync_now_ms, duration_ms=int(PENALTY_RETRACT_SPEED*sf), flip=True)
                self.is_penalty = True 
                
        if self.shake_until_ms > sync_now_ms: 
            self.current_pos = (self.target_pos[0] + random.randint(-4, 4), self.target_pos[1] + random.randint(-4, 4))
        elif self.is_penalty and self.penalty_phase == 1:
            self.current_pos = self.target_pos

        if not self.is_animating:
            self.scale_y = 1.0
            return False

        elapsed = sync_now_ms - self.anim_start_ms
        t_linear = min(1.0, elapsed / max(1, self.duration_ms))
        
        if t_linear >= 1.0:
            if self.is_penalty: 
                return self._handle_penalty_logic(sync_now_ms)
            elif self.pending_bounce_target:
                if self.perform_flip:
                    self.face_up = not self.face_up
                next_target = self.pending_bounce_target
                self.pending_bounce_target = None
                spin_angle = random.uniform(720, 1080) * random.choice([-1, 1])
                sf = getattr(self, 'sf', 1)
                self.start_animation(self.target_pos, next_target, sync_now_ms, duration_ms=int(500*sf), flip=False, target_angle=spin_angle, easing=ease_out_quad)
                return True
            else:
                self.is_animating = False
                self.current_pos = self.target_pos
                self.angle = self.target_angle
                self.skew_angle = self.target_angle 
                if self.perform_flip:
                    self.face_up = not self.face_up
            self.scale_y = 1.0
        else:
            ts = self.easing_func(t_linear)
            self.current_pos = (
                self.start_pos[0] + (self.target_pos[0] - self.start_pos[0]) * ts,
                self.start_pos[1] + (self.target_pos[1] - self.start_pos[1]) * ts
            )
            self.angle = self.start_angle + (self.target_angle - self.start_angle) * ts
            
            if self.perform_flip:
                self.scale_y = abs(math.cos(t_linear * math.pi))
            else:
                self.scale_y = 1.0
                
        return True

    def __eq__(self, other):
        return isinstance(other, Card) and self.rank == other.rank


class ScoopManager:
    def __init__(self): 
        self.active = False
        
    def start(self, piles, p1h, p2h, p1d, p2d, pile_rects, sync_now_ms):
        self.active, self.phase = True, 0
        self.next_action_at_ms = sync_now_ms
        self.p1h, self.p2h, self.p1d, self.p2d = p1h, p2h, p1d, p2d
        self.cards, self.cpu_cards = [], []
        self.piles_data = {}
        self.launched_piles = []
        self.pair_index = 0
        
        for i in range(8):
            self.piles_data[i] = piles[i][:]
            piles[i].clear()
            for c in self.piles_data[i]:
                gx, gy = pile_rects[i].x, pile_rects[i].y
                c.current_pos = c.target_pos = (gx, gy)
                c.face_up = True
                
    def update(self, sync_now_ms, sf=1):
        if not self.active: return "RUNNING"
        
        if self.phase == 0:
            if self.pair_index < 4:
                if sync_now_ms >= self.next_action_at_ms:
                    for i, h in [(self.pair_index, self.p2h), (self.pair_index + 4, self.p1h)]:
                        self.launched_piles.append(i)
                        for c in self.piles_data[i]:
                            c.start_animation(c.current_pos, (h[0] + 10 + random.randint(-15, 15), h[1] + 5 + random.randint(-15, 15)), sync_now_ms, duration_ms=int(SCOOP_SPEED*sf), flip=False, easing=ease_linear)
                            (self.cpu_cards if i < 4 else self.cards).append(c)
                    self.pair_index += 1
                    self.next_action_at_ms = sync_now_ms + int(66 * sf)
            elif self.pair_index == 4 and all(not c.is_animating for c in self.cards + self.cpu_cards): 
                self.phase = 1
                self.next_action_at_ms = sync_now_ms + int(PAUSE_DURATION * sf)
                
        elif self.phase == 1:
            if sync_now_ms >= self.next_action_at_ms:
                for c in self.cards + self.cpu_cards: c.start_animation(c.current_pos, c.current_pos, sync_now_ms, duration_ms=int(FLIP_SPEED*sf), flip=True)
                self.phase = 2
                
        elif self.phase == 2:
            if all(not c.is_animating for c in self.cards + self.cpu_cards):
                self.phase = 3
                self.next_action_at_ms = sync_now_ms + int(PAUSE_DURATION * sf)
            
        elif self.phase == 3:
            if sync_now_ms >= self.next_action_at_ms:
                for stack, base in [(self.cards, self.p1h), (self.cpu_cards, self.p2h)]:
                    for i, c in enumerate(stack): 
                        c.make_neat()
                        c.start_animation(c.current_pos, (base[0], base[1] - ((len(stack) - 1 - i) * 0.5)), sync_now_ms, duration_ms=int(NEAT_SPEED*sf), target_angle=0)
                self.phase = 4
                
        elif self.phase == 4:
            if all(not c.is_animating for c in self.cards + self.cpu_cards):
                self.phase = 5
                self.next_action_at_ms = sync_now_ms + int(PAUSE_DURATION * sf)
            
        elif self.phase == 5:
            if sync_now_ms >= self.next_action_at_ms:
                for stack, dest in [(self.cards, self.p1d), (self.cpu_cards, self.p2d)]:
                    for c in stack: c.start_animation(c.current_pos, dest, sync_now_ms, duration_ms=int(SCOOP_SPEED*sf), easing=ease_out_quad)
                self.phase = 6
                
        elif self.phase == 6 and all(not c.is_animating for c in self.cards + self.cpu_cards): 
            self.active = False
            return "DONE"
            
        for c in self.cards + self.cpu_cards: c.update(sync_now_ms)
        return "RUNNING"

class Deck:
    def __init__(self, cards=None):
        self.cards = cards if cards else []
    def shuffle(self): random.shuffle(self.cards)
    def pop_top(self): 
        if self.cards:
            c = self.cards.pop(0)
            c.regenerate_layout()
            return c
        return None
    def add_bottom(self, cards): self.cards.extend(cards)
    def is_empty(self): return len(self.cards) == 0

class Button:
    def __init__(self, text, x_ratio, y_ratio, w_ratio, h_ratio, action_state):
        self.x_ratio, self.y_ratio = x_ratio, y_ratio
        self.w_ratio, self.h_ratio = w_ratio, h_ratio
        self.text, self.action_state, self.is_hovered = text, action_state, False
        self.rect = pygame.Rect(0,0,0,0)

    def update_rect(self, screen_w, screen_h):
        self.rect = pygame.Rect(
            int(self.x_ratio * screen_w), 
            int(self.y_ratio * screen_h), 
            int(self.w_ratio * screen_w), 
            int(self.h_ratio * screen_h)
        )

    def draw(self, surface, font):
        pygame.draw.rect(surface, BUTTON_HOVER_COLOR if self.is_hovered else BUTTON_COLOR, self.rect, border_radius=10)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2, border_radius=10)
        ts = font.render(self.text, True, (255, 255, 255))
        surface.blit(ts, ts.get_rect(center=self.rect.center))

    def check_hover(self, mx, my): self.is_hovered = self.rect.collidepoint(mx, my)
    def check_click(self, mx, my): return self.action_state if self.rect.collidepoint(mx, my) else None

class Slider:
    def __init__(self, x_ratio, y_ratio, w_ratio, h_ratio, min_val, max_val, step, initial_val):
        self.x_ratio = x_ratio
        self.y_ratio = y_ratio
        self.w_ratio = w_ratio
        self.h_ratio = h_ratio
        self.min_val = min_val
        self.max_val = max_val
        self.step = step
        self.val = initial_val
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.handle_rect = pygame.Rect(0, 0, 0, 0)
        self.is_dragging = False

    def update_rect(self, screen_w, screen_h):
        self.rect = pygame.Rect(
            int(self.x_ratio * screen_w), 
            int(self.y_ratio * screen_h), 
            int(self.w_ratio * screen_w), 
            int(self.h_ratio * screen_h)
        )
        self._update_handle_from_val()

    def _update_handle_from_val(self):
        if self.rect.w == 0: return
        ratio = (self.val - self.min_val) / (self.max_val - self.min_val)
        hx = self.rect.x + int(ratio * self.rect.w)
        self.handle_rect = pygame.Rect(hx - 10, self.rect.y - 10, 20, self.rect.h + 20)

    def handle_event(self, event, mx, my):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.handle_rect.collidepoint(mx, my):
                self.is_dragging = True
            elif event.button == 1 and self.rect.collidepoint(mx, my):
                self._set_val_from_x(mx)
                self.is_dragging = True
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.is_dragging = False
        elif event.type == pygame.MOUSEMOTION:
            if self.is_dragging:
                self._set_val_from_x(mx)

    def _set_val_from_x(self, x):
        x = max(self.rect.x, min(x, self.rect.x + self.rect.w))
        ratio = (x - self.rect.x) / self.rect.w
        raw_val = self.min_val + ratio * (self.max_val - self.min_val)
        self.val = int(round(raw_val / self.step) * self.step)
        self._update_handle_from_val()

    def set_val(self, new_val):
        self.val = int(max(self.min_val, min(new_val, self.max_val)))
        self._update_handle_from_val()
        
    def draw(self, surface, font):
        pygame.draw.rect(surface, (100, 100, 100), self.rect, border_radius=5)
        fill_w = self.handle_rect.centerx - self.rect.x
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.h)
        pygame.draw.rect(surface, (150, 200, 255), fill_rect, border_radius=5)
        pygame.draw.rect(surface, (255, 255, 255), self.handle_rect, border_radius=5)
        pygame.draw.rect(surface, (50, 50, 50), self.handle_rect, 2, border_radius=5)

class TextInputBox:
    def __init__(self, x_ratio, y_ratio, w_ratio, h_ratio, initial_text="", max_length=16):
        self.x_ratio, self.y_ratio = x_ratio, y_ratio
        self.w_ratio, self.h_ratio = w_ratio, h_ratio
        self.text = initial_text
        self.max_length = max_length
        self.rect = pygame.Rect(0, 0, 0, 0)

    def update_rect(self, screen_w, screen_h):
        self.rect = pygame.Rect(
            int(self.x_ratio * screen_w),
            int(self.y_ratio * screen_h),
            int(self.w_ratio * screen_w),
            int(self.h_ratio * screen_h)
        )

    def handle_event(self, event):
        if event.type == pygame.TEXTINPUT:
            if len(self.text) < self.max_length:
                self.text += event.text
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]

    def draw(self, surface, font):
        pygame.draw.rect(surface, (255, 255, 255), self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 100, 100), self.rect, 2, border_radius=8)
        ts = font.render(self.text + "|", True, (0, 0, 0))
        surface.blit(ts, (self.rect.x + 10, self.rect.y + (self.rect.h - ts.get_height()) // 2))

class Checkbox:
    def __init__(self, x_ratio, y_ratio, size_ratio, text, action_state, initial_val=False):
        self.x_ratio, self.y_ratio = x_ratio, y_ratio
        self.size_ratio = size_ratio
        self.text, self.action_state, self.is_hovered = text, action_state, False
        self.val = initial_val
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.hitbox = pygame.Rect(0, 0, 0, 0)

    def update_rect(self, screen_w, screen_h):
        size = int(self.size_ratio * screen_h)
        self.rect = pygame.Rect(
            int(self.x_ratio * screen_w), 
            int(self.y_ratio * screen_h), 
            size, size
        )
        self.hitbox = pygame.Rect(self.rect.x, self.rect.y, size * 6, size)

    def draw(self, surface, font):
        pygame.draw.rect(surface, BUTTON_HOVER_COLOR if self.is_hovered else (255, 255, 255), self.rect, 2, border_radius=3)
        if self.val:
            inner = self.rect.inflate(-8, -8)
            pygame.draw.rect(surface, (100, 255, 100), inner, border_radius=2)
        
        ts = font.render(self.text, True, (255, 255, 255))
        surface.blit(ts, (self.rect.right + 10, self.rect.centery - ts.get_height() // 2))
        self.hitbox = pygame.Rect(self.rect.x, self.rect.y, self.rect.w + 10 + ts.get_width(), self.rect.h)

    def check_hover(self, mx, my): 
        self.is_hovered = self.hitbox.collidepoint(mx, my)

    def check_click(self, mx, my): 
        if self.hitbox.collidepoint(mx, my):
            self.val = not self.val
            return self.action_state
        return None