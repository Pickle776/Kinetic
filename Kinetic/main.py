# main.py
import pygame
import sys
import os
import time
import math
import random
import threading
import queue
from config import *
from engine import KineticEngine, SequenceScheduler
from game_objects import Card, Button, Slider, TextInputBox, ScoopManager, Checkbox
from graphics import Renderer
from bot import Bot
from network import NetworkManager

def fmt_time(current_ms, start_ms):
    elapsed = max(0, current_ms - start_ms)
    s = elapsed / 1000.0
    m = int(s // 60)
    sec = s % 60
    return f"[T+{m}:{sec:06.3f}]"

# Console worker thread logic
def console_worker(cmd_queue):
    print("\n--- KINETIC CONSOLE ACTIVE ---")
    print("Commands can be chained with ';'")
    print("  play <p_id> <pile>   (e.g., 'play 1 3')")
    print("  stuck <p_id>         (e.g., 'stuck 1')")
    print("  wait <ms>            (e.g., 'wait 50')")
    print("------------------------------")
    print("Examples:")
    print("  Simultaneous: play 1 0 ; play 2 0")
    print("  Staggered:    play 1 0 ; wait 50 ; play 2 0")
    print("  quit / exit")
    print("------------------------------\n")
    while True:
        try:
            cmd = input().strip().lower()
            if cmd:
                cmd_queue.put(cmd)
        except (EOFError, KeyboardInterrupt):
            break

def execute_play(p_id, pile_idx, engine, renderer, current_time_ms, sync_now_ms, source="SYS", sf=1, local_p_id=1, match_start_time=0):
    deck_pos = renderer.DeckP1_Pos if p_id == local_p_id else renderer.DeckP2_Pos
    top_card = engine.decks[p_id].cards[0] if not engine.decks[p_id].is_empty() else None
    
    success, reason = engine.attempt_play(p_id, pile_idx, current_time_ms)
    t_str = fmt_time(sync_now_ms, match_start_time)
    
    if success:
        played_card = engine.piles[pile_idx][-1]
        played_card.start_animation(deck_pos, renderer.pile_rects[pile_idx].topleft, sync_now_ms, duration_ms=int(250*sf), flip=True)
    elif reason == "invalid" and top_card:
        print(f"{t_str} [{source}] P{p_id} misplayed on pile {pile_idx}. Penalty locked.")
        top_card.trigger_penalty(deck_pos, renderer.pile_rects[pile_idx].topleft, sync_now_ms, sf=sf)
    elif reason == "bump":
        print(f"{t_str} [{source}] P{p_id} was BUMPED on pile {pile_idx}!")
        bumped_card = engine.bumps[p_id][-1]
        skirt_x = renderer.BoardStartX - 100 if random.random() > 0.5 else renderer.BoardStartX + renderer.BoardWidth + 100
        skirt_y = random.randint(100, BASE_H - 100)
        bumped_card.trigger_bump(deck_pos, renderer.pile_rects[pile_idx].topleft, (skirt_x, skirt_y), sync_now_ms, sf=sf)
    elif reason == "penalized":
        print(f"{t_str} [{source}] P{p_id} attempted play but is currently PENALIZED.")
    elif reason == "empty_deck":
        print(f"{t_str} [{source}] P{p_id} attempted play but their deck is EMPTY.")
        
    return success

def create_full_deck():
    suits = ['H', 'D', 'C', 'S']
    ranks = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    deck = [Card(r, s) for s in suits for r in ranks]
    random.shuffle(deck)
    return deck

def load_player_data():
    name = f"Player_{random.randint(1000, 9999)}"
    rating = 1000
    if os.path.exists("rating.txt"):
        with open("rating.txt", "r") as f:
            lines = f.readlines()
            if len(lines) > 0:
                name = lines[0].strip()
            if len(lines) > 1:
                try:
                    rating = int(lines[1].strip())
                except ValueError:
                    pass
    else:
        save_player_data(name, rating)
    return name, rating

def save_player_data(name, rating):
    with open("rating.txt", "w") as f:
        f.write(f"{name}\n{rating}")

def main():
    pygame.init()
    screen = pygame.display.set_mode((BASE_W, BASE_H), pygame.RESIZABLE)
    pygame.display.set_caption("Kinetic")
    clock = pygame.time.Clock()

    renderer = Renderer(screen)
    renderer.calculate_layout(BASE_W, BASE_H)
    slowmo_font = pygame.font.SysFont("Arial", 20, bold=True)
    
    engine = KineticEngine()
    bot = None
    bot_config = {"auto_stuck": True}
    scoop_manager = ScoopManager()
    scheduler = SequenceScheduler()
    player_name, player_rating = load_player_data()
    
    cmd_queue = queue.Queue()
    input_thread = threading.Thread(target=console_worker, args=(cmd_queue,), daemon=True)
    input_thread.start()
    
    scheduled_commands = [] 
    pending_play_intents = []
    
    current_state = STATE_MENU
    current_mode = None
    current_bot_rating = None
    show_debug = True 
    slow_mo = False
    
    deal_step = 0
    deal_next_action_ms = 0
    stuck_shake_until_ms = 0
    winner_msg = ""
    match_start_time = 0

    lan_network_manager = None
    lan_status_text = ""
    lan_timed_out = False
    peer_list = []
    peer_buttons = []
    is_host = False
    opponent_name = ""
    show_name_input = False
    
    bot_input_active = False
    bot_input_text = ""
    bot_val_rect = pygame.Rect(0, 0, 0, 0)

    # Network state tracking
    clock_offset = 0
    local_p_id = 1
    remote_p_id = 2
    local_rematch_requested = False
    remote_rematch_requested = False
    rematch_seed = None

    menu_buttons = [
        Button("Practice Solo", 0.5 - (150/BASE_W), 0.5 - (100/BASE_H), 300/BASE_W, 60/BASE_H, MODE_SINGLE),
        Button("Vs Computer", 0.5 - (150/BASE_W), 0.5 - (20/BASE_H), 300/BASE_W, 60/BASE_H, STATE_BOT_SELECT), 
        Button("Play Online / LAN", 0.5 - (150/BASE_W), 0.5 + (60/BASE_H), 300/BASE_W, 60/BASE_H, STATE_MP_MODE_SELECT),
        Button("Help / Rules", 0.5 - (150/BASE_W), 0.5 + (140/BASE_H), 300/BASE_W, 60/BASE_H, STATE_HELP)
    ]

    mp_mode_buttons = [
        Button("LAN (Local Network)", 0.5 - (150/BASE_W), 0.4, 300/BASE_W, 60/BASE_H, "LAN"),
        Button("Online (WIP)", 0.5 - (150/BASE_W), 0.55, 300/BASE_W, 60/BASE_H, "ONLINE"),
        Button("Back", 0.5 - (150/BASE_W), 0.7, 300/BASE_W, 60/BASE_H, STATE_MENU)
    ]

    wip_buttons = [
        Button("Back", 0.5 - (150/BASE_W), 0.5, 300/BASE_W, 60/BASE_H, STATE_MP_MODE_SELECT)
    ]
    
    mp_cancel_btn = [Button("Cancel", 0.5 - (150/BASE_W), 0.85, 300/BASE_W, 60/BASE_H, "CANCEL")]
    lan_retry_btn = Button("Keep Waiting", 0.5 - (150/BASE_W), 0.70, 300/BASE_W, 60/BASE_H, "RETRY")
    edit_name_btn = Button("Edit", 0.5 + (80/BASE_W), 0.23, 70/BASE_W, 30/BASE_H, "EDIT_NAME")

    game_over_buttons = [
        Button("Play Again", 0.5 - (150/BASE_W), 0.5, 300/BASE_W, 60/BASE_H, "PLAY_AGAIN"),
        Button("Main Menu", 0.5 - (150/BASE_W), 0.5 + (80/BASE_H), 300/BASE_W, 60/BASE_H, STATE_MENU)
    ]
    
    back_button = Button("Back", 0.5 - (150/BASE_W), 0.85, 300/BASE_W, 60/BASE_H, STATE_MENU)
    slowmo_btn = Button("SlowMo: OFF", 0.02, 0.90, 150/BASE_W, 50/BASE_H, "SLOWMO")
    
    name_input = TextInputBox(0.5 - (200 / BASE_W), 0.30, 400 / BASE_W, 60 / BASE_H, initial_text=player_name)

    # Bot Selection UI
    initial_bot_rating = int(math.ceil(player_rating / 10.0)) * 10
    initial_bot_rating = max(0, min(1000, initial_bot_rating))
    
    bot_slider = Slider(0.5 - (200/BASE_W), 0.45, 400/BASE_W, 20/BASE_H, 0, 1000, 10, initial_bot_rating)
    bot_minus_btn = Button("- 1", 0.5 - (260/BASE_W), 0.43, 50/BASE_W, 40/BASE_H, "MINUS_1")
    bot_plus_btn = Button("+ 1", 0.5 + (210/BASE_W), 0.43, 50/BASE_W, 40/BASE_H, "PLUS_1")
    bot_start_btn = Button("Start Match", 0.5 - (150/BASE_W), 0.6, 300/BASE_W, 60/BASE_H, "START_BOT")
    bot_back_btn = Button("Back", 0.5 - (150/BASE_W), 0.75, 300/BASE_W, 60/BASE_H, STATE_MENU)

    bot_ui_elements = [bot_slider, bot_minus_btn, bot_plus_btn, bot_start_btn, bot_back_btn]

    # Dev Buttons
    auto_stuck_btn = Checkbox(1.0 - (210/BASE_W), 150/BASE_H, 24/BASE_H, "Auto-Stuck", "TOGGLE_AUTO_STUCK", initial_val=bot_config["auto_stuck"])
    dev_btns = [auto_stuck_btn]

    all_btns = menu_buttons + game_over_buttons + mp_cancel_btn + [back_button, slowmo_btn, lan_retry_btn, edit_name_btn] + mp_mode_buttons + wip_buttons + dev_btns
    for btn in all_btns + bot_ui_elements:
        if hasattr(btn, 'update_rect'):
            btn.update_rect(BASE_W, BASE_H)
    name_input.update_rect(BASE_W, BASE_H)

    stuck_btn = Button("STUCK", 0.0, 0.0, 100/BASE_W, 50/BASE_H, "STUCK")
    stuck_btn.rect = pygame.Rect(renderer.BoardStartX + renderer.BoardWidth + 20, (BASE_H // 2) - 25, 100, 50)

    print("[SYS] Game initialized. Entering MENU.")
    running = True
    while running:
        current_time_ms = int(time.time() * 1000)
        mx, my = pygame.mouse.get_pos()
        sf = 10 if slow_mo else 1
        
        # Single sync clock computed once per tick
        sync_now_ms = current_time_ms + clock_offset
        
        # ---------------------------------------------------------
        # NETWORK POLLING
        # ---------------------------------------------------------
        if lan_network_manager:
            for event in lan_network_manager.poll_events():
                if event["type"] == "DISCOVERING":
                    discovery_elapsed = event.get("elapsed", 0)
                    if not lan_timed_out:
                        lan_status_text = f"Searching for an opponent on your network... ({int(discovery_elapsed)}s)"
                elif event["type"] == "CONNECTED":
                    opponent_name = event["opponent_name"]
                    is_host = event["is_host"]
                    clock_offset = event.get("offset", 0)
                    local_p_id = 1 if is_host else 2
                    remote_p_id = 2 if is_host else 1
                    
                    local_rematch_requested = False
                    remote_rematch_requested = False
                    rematch_seed = None
                    
                    # Seed RNG so both machines shuffle deck identically!
                    match_seed = event.get("seed", 0)
                    random.seed(match_seed)
                    
                    # Schedule Match Start sequence for exactly 2 real seconds from now
                    scheduler.schedule("MATCH_START", sync_now_ms + 2000)
                    current_state = STATE_MATCH_STARTING
                elif event["type"] == "MULTIPLE_FOUND":
                    peer_list = event["peers"]
                    current_state = STATE_LAN_PEER_PICKER
                    peer_buttons = []
                    for i, peer in enumerate(peer_list):
                        btn = Button(peer["name"], 0.5 - (150/BASE_W), 0.35 + (i * 0.1), 300/BASE_W, 60/BASE_H, f"PEER_{i}")
                        btn.update_rect(screen.get_width(), screen.get_height())
                        peer_buttons.append(btn)
                elif event["type"] == "TIMEOUT":
                    lan_timed_out = True
                elif event["type"] == "DISCONNECT":
                    print("[SYS] Connection lost to opponent.")
                    # TODO (Disconnect Bug): If connection drops exactly during STATE_SCOOPING or 
                    # STATE_DEALING, background lists (like scoop_manager arrays) might be left 
                    # fragmented since we force an immediate transition to GAME_OVER without cleanup.
                    if current_state in [STATE_PLAYING, STATE_DEALING, STATE_SCOOPING, STATE_MATCH_STARTING, STATE_GAME_OVER]:
                        winner_msg = "CONNECTION LOST"
                        current_state = STATE_GAME_OVER
                        local_rematch_requested = False
                        remote_rematch_requested = False
                        lan_network_manager = None
                elif event["type"] == "NET_MSG":
                    msg = event["data"]
                    if msg.get("type") == "play":
                        pending_play_intents.append({
                            "type": "play",
                            "p_id": msg["p_id"], 
                            "pile": msg["pile"], 
                            "timestamp": msg["time"], 
                            "source": "REMOTE"
                        })
                    elif msg.get("type") == "pickup":
                        pending_play_intents.append({
                            "type": "pickup",
                            "p_id": msg["p_id"],
                            "timestamp": msg["time"],
                            "source": "REMOTE"
                        })
                    elif msg.get("type") == "stuck":
                        engine.stuck_calls[msg["p_id"]] = msg.get("time", sync_now_ms)
                        print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P{msg['p_id']} called STUCK.")
                    elif msg.get("type") == "rematch":
                        remote_rematch_requested = True
                        if "seed" in msg:
                            rematch_seed = msg["seed"]
                    elif msg.get("type") == "cancel":
                        print("[SYS] Opponent cancelled rematch / left.")
                        if current_state in [STATE_GAME_OVER, STATE_PLAYING, STATE_DEALING, STATE_SCOOPING, STATE_MATCH_STARTING]:
                            winner_msg = "OPPONENT LEFT"
                            current_state = STATE_GAME_OVER
                            local_rematch_requested = False
                            remote_rematch_requested = False
                            if lan_network_manager:
                                lan_network_manager.cancel()
                                lan_network_manager = None

        # ---------------------------------------------------------
        # REMATCH SYNCHRONIZATION
        # ---------------------------------------------------------
        if local_rematch_requested and remote_rematch_requested:
            if current_mode == MODE_LAN and rematch_seed is not None:
                random.seed(rematch_seed)
            engine.setup_game(create_full_deck())
            if current_mode == MODE_LAN:
                random.seed() # Unseed immediately after shuffling!
            current_state = STATE_DEALING
            deal_step = 0
            deal_next_action_ms = sync_now_ms + int(333 * sf)
            pending_play_intents.clear()
            local_rematch_requested = False
            remote_rematch_requested = False

        # ---------------------------------------------------------
        # SCHEDULED SEQUENCES
        # ---------------------------------------------------------
        seq, args = scheduler.check(sync_now_ms)
        if seq == "MATCH_START":
            current_mode = MODE_LAN
            engine.setup_game(create_full_deck())
            random.seed() # Unseed immediately to not break future games
            current_state = STATE_DEALING
            deal_step = 0
            deal_next_action_ms = sync_now_ms + int(333 * sf) # 20 frames delay
            bot = None
            pending_play_intents.clear()
            print("[SYS] Transitioned to STATE_DEALING (Multiplayer Scrim).")
        elif seq == "SCOOP":
            current_state = STATE_SCOOPING
            print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] SCOOP INITIATED.")
            heap_x = renderer.BoardStartX + renderer.BoardWidth + 20
            p1_heap = (heap_x, (BASE_H // 2) + 20)
            p2_heap = (heap_x, (BASE_H // 2) - renderer.CardH - 20)
            scoop_manager.start(engine.piles, p1_heap, p2_heap, renderer.DeckP1_Pos, renderer.DeckP2_Pos, renderer.pile_rects, sync_now_ms)


        if current_state == STATE_PLAYING:
            # TODO (Netcode Bug): Delay-based netcode without rollback will desync here if a 
            # remote packet takes longer than INPUT_DELAY_MS (32ms) to arrive. The late intent 
            # will execute out-of-order, causing an irrecoverable state desync between clients.
            ready_intents, pending_play_intents = engine.get_ready_intents(pending_play_intents, sync_now_ms, INPUT_DELAY_MS)
            for intent in ready_intents:
                if intent.get("type", "play") == "play":
                    is_success = execute_play(intent["p_id"], intent["pile"], engine, renderer, intent["timestamp"], sync_now_ms, source=intent.get("source", "SYS"), sf=sf, local_p_id=local_p_id, match_start_time=match_start_time)
                    if is_success:
                        scheduler.cancel() # Cancel any scheduled SCOOP if board un-sticks!
                elif intent.get("type") == "pickup":
                    p_id = intent["p_id"]
                    deck_pos = renderer.DeckP1_Pos if p_id == local_p_id else renderer.DeckP2_Pos
                    for c in engine.bumps[p_id]:
                        if not c.is_returning:
                            c.start_return_animation(deck_pos, sync_now_ms, sf=sf)
                            break
            
            engine.update_valid_targets()
            
            # --- BOT HOOK UPDATE ---
            if bot:
                bot_action = bot.update(engine, sync_now_ms, sf=sf, auto_stuck=bot_config.get("auto_stuck", False), match_start_time=match_start_time)
                if bot_action:
                    if bot_action["type"] == "play":
                        pending_play_intents.append({
                            "type": "play",
                            "p_id": bot_action["p_id"],
                            "pile": bot_action["pile"],
                            "timestamp": sync_now_ms,
                            "source": "BOT"
                        })
                    elif bot_action["type"] == "stuck":
                        engine.stuck_calls[bot_action["p_id"]] = sync_now_ms
                        print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P{bot_action['p_id']} called STUCK.")

        # ---------------------------------------------------------
        # RESOLVE RETURNING CARDS
        # ---------------------------------------------------------
        for p_id in [1, 2]:
            for c in engine.bumps[p_id][:]:
                if c.is_returning and not c.is_animating:
                    engine.bumps[p_id].remove(c)
                    c.make_neat()
                    engine.decks[p_id].add_bottom([c])
                    c.is_returning = False

        # ---------------------------------------------------------
        # HOVER DETECTION FOR BUMPED CARDS
        # ---------------------------------------------------------
        for p_id in [1, 2]:
            for c in engine.bumps[p_id]:
                c.is_hovered = False

        hovered_card = None
        hovered_pid = None
        if current_state == STATE_PLAYING:
            for p_id in [2, 1]:
                for c in reversed(engine.bumps[p_id]):
                    if c.is_returning: continue
                    r = pygame.Rect(c.current_pos[0] - c.skew_offset[0], c.current_pos[1] - c.skew_offset[1], renderer.CardW, renderer.CardH)
                    if r.collidepoint((mx, my)):
                        hovered_card = c
                        hovered_pid = p_id
                        break
                if hovered_card: break
            
            if hovered_card:
                hovered_card.is_hovered = True

        # ---------------------------------------------------------
        # PROCESS BACKGROUND CONSOLE COMMANDS & SCHEDULING
        # ---------------------------------------------------------
        while not cmd_queue.empty():
            raw_cmd = cmd_queue.get()
            if raw_cmd in ['quit', 'exit']:
                running = False
                continue
                
            sequence = [c.strip().split() for c in raw_cmd.split(';') if c.strip()]
            accumulated_delay = 0
            
            for parts in sequence:
                if not parts: continue
                if parts[0] == 'wait' and len(parts) == 2:
                    try:
                        accumulated_delay += int(parts[1])
                    except ValueError:
                        pass
                else:
                    scheduled_commands.append((sync_now_ms + accumulated_delay, parts))

        remaining_cmds = []
        for exec_time, parts in scheduled_commands:
            if sync_now_ms >= exec_time:
                if current_state != STATE_PLAYING:
                    continue 
                    
                if parts[0] == 'play' and len(parts) == 3:
                    try:
                        p_id = int(parts[1])
                        pile_idx = int(parts[2])
                        if p_id in [1, 2] and 0 <= pile_idx <= 7:
                            t = sync_now_ms
                            pending_play_intents.append({
                                "type": "play",
                                "p_id": p_id, 
                                "pile": pile_idx, 
                                "timestamp": t, 
                                "source": "CONSOLE"
                            })
                    except ValueError:
                        pass
                elif parts[0] == 'stuck' and len(parts) == 2:
                    try:
                        p_id = int(parts[1])
                        if p_id in [1, 2]:
                            engine.stuck_calls[p_id] = sync_now_ms
                            print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P{p_id} called STUCK (via Console).")
                    except ValueError:
                        pass
            else:
                remaining_cmds.append((exec_time, parts))
        scheduled_commands = remaining_cmds

        # ---------------------------------------------------------
        # PROCESS PYGAME UI EVENTS
        # ---------------------------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            elif event.type == pygame.VIDEORESIZE:
                renderer.calculate_layout(event.w, event.h)
                for btn in all_btns + bot_ui_elements:
                    if hasattr(btn, 'update_rect'):
                        btn.update_rect(event.w, event.h)
                for btn in peer_buttons:
                    btn.update_rect(event.w, event.h)
                name_input.update_rect(event.w, event.h)
                stuck_btn.rect = pygame.Rect(renderer.BoardStartX + renderer.BoardWidth + 20, (event.h // 2) - 25, 100, 50)

            if current_state == STATE_MP_MODE_SELECT and show_name_input:
                name_input.handle_event(event)
                
            if current_state == STATE_BOT_SELECT:
                bot_slider.handle_event(event, mx, my)
                if bot_slider.is_dragging and bot_input_active:
                    bot_input_active = False
                    if bot_input_text.strip():
                        try:
                            nv = int(bot_input_text)
                            nv = int(round(nv / 10.0) * 10)
                            bot_slider.set_val(nv)
                        except ValueError:
                            pass
                    bot_input_text = ""

            if event.type == pygame.KEYDOWN:
                if current_state == STATE_MP_MODE_SELECT and show_name_input and event.key == pygame.K_RETURN:
                    show_name_input = False
                    if name_input.text.strip():
                        player_name = name_input.text.strip()
                        save_player_data(player_name, player_rating)
                elif current_state == STATE_BOT_SELECT and bot_input_active:
                    if event.key == pygame.K_RETURN:
                        bot_input_active = False
                        if bot_input_text.strip():
                            try:
                                nv = int(bot_input_text)
                                nv = int(round(nv / 10.0) * 10)
                                bot_slider.set_val(nv)
                            except ValueError:
                                pass
                        bot_input_text = ""
                    elif event.key == pygame.K_BACKSPACE:
                        bot_input_text = bot_input_text[:-1]
                    elif event.unicode.isdigit() or (event.unicode == '-' and len(bot_input_text) == 0):
                        if len(bot_input_text) < 5:
                            bot_input_text += event.unicode
                elif event.key == pygame.K_ESCAPE:
                    current_state = STATE_MENU
                    if lan_network_manager:
                        lan_network_manager.send_message({"type": "cancel"})
                        lan_network_manager.cancel()
                        lan_network_manager = None
                elif event.key == pygame.K_r:
                    show_debug = not show_debug
                elif current_state == STATE_PLAYING and event.key in [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8]:
                    key_map = {
                        pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
                        pygame.K_5: 4, pygame.K_6: 5, pygame.K_7: 6, pygame.K_8: 7
                    }
                    pile_idx = key_map[event.key]
                    if current_mode == MODE_LAN:
                        t = sync_now_ms
                        pending_play_intents.append({
                            "type": "play",
                            "p_id": local_p_id, 
                            "pile": pile_idx, 
                            "timestamp": t, 
                            "source": "KEYBOARD"
                        })
                        if lan_network_manager:
                            lan_network_manager.send_message({"type": "play", "p_id": local_p_id, "pile": pile_idx, "time": t})
                    else:
                        pending_play_intents.append({"type": "play", "p_id": 1, "pile": pile_idx, "timestamp": sync_now_ms, "source": "KEYBOARD"})
                        pending_play_intents.append({"type": "play", "p_id": 2, "pile": pile_idx, "timestamp": sync_now_ms, "source": "KEYBOARD"})

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if show_debug:
                    if slowmo_btn.check_click(mx, my):
                        slow_mo = not slow_mo
                        slowmo_btn.text = "SlowMo: ON" if slow_mo else "SlowMo: OFF"
                        continue
                    
                    dev_btn_clicked = False
                    for btn in dev_btns:
                        res = btn.check_click(mx, my)
                        if res == "TOGGLE_AUTO_STUCK":
                            bot_config["auto_stuck"] = btn.val
                            dev_btn_clicked = True
                    if dev_btn_clicked:
                        continue

                if current_state == STATE_MENU:
                    for btn in menu_buttons:
                        res = btn.check_click(mx, my)
                        if res == STATE_HELP:
                            current_state = STATE_HELP
                        elif res == STATE_BOT_SELECT:
                            current_state = STATE_BOT_SELECT
                        elif res == STATE_MP_MODE_SELECT:
                            current_state = STATE_MP_MODE_SELECT
                        elif res == MODE_SINGLE:
                            os.system('cls' if os.name == 'nt' else 'clear')
                            current_mode = res
                            engine.setup_game(create_full_deck())
                            current_state = STATE_DEALING
                            deal_step = 0
                            deal_next_action_ms = sync_now_ms + int(333 * sf)
                            bot = None
                            pending_play_intents.clear()
                            
                elif current_state == STATE_MP_MODE_SELECT:
                    for btn in mp_mode_buttons:
                        res = btn.check_click(mx, my)
                        if res == "LAN":
                            lan_network_manager = NetworkManager(player_name)
                            lan_network_manager.start()
                            lan_status_text = "Searching for an opponent on your network…"
                            lan_timed_out = False
                            current_state = STATE_LAN_CONNECTING
                        elif res == "ONLINE":
                            current_state = STATE_ONLINE_WIP
                        elif res == STATE_MENU:
                            current_state = STATE_MENU
                            
                    if edit_name_btn.check_click(mx, my):
                        show_name_input = not show_name_input
                        if not show_name_input:
                            if name_input.text.strip():
                                player_name = name_input.text.strip()
                                save_player_data(player_name, player_rating)

                elif current_state == STATE_ONLINE_WIP:
                    for btn in wip_buttons:
                        if btn.check_click(mx, my) == STATE_MP_MODE_SELECT:
                            current_state = STATE_MP_MODE_SELECT

                elif current_state == STATE_LAN_CONNECTING:
                    if mp_cancel_btn[0].check_click(mx, my):
                        if lan_network_manager:
                            lan_network_manager.cancel()
                        current_state = STATE_MP_MODE_SELECT
                    elif lan_timed_out and lan_retry_btn.check_click(mx, my):
                        lan_timed_out = False
                        if lan_network_manager:
                            lan_network_manager.start()

                elif current_state == STATE_LAN_PEER_PICKER:
                    for i, peer in enumerate(peer_list):
                        if peer_buttons[i].check_click(mx, my):
                            if lan_network_manager:
                                lan_network_manager.connect_to_peer(peer["ip"])
                            lan_status_text = f"Connecting to {peer['name']}…"
                            current_state = STATE_LAN_CONNECTING
                    if mp_cancel_btn[0].check_click(mx, my):
                        if lan_network_manager:
                            lan_network_manager.cancel()
                        current_state = STATE_MP_MODE_SELECT

                elif current_state == STATE_HELP:
                    if back_button.check_click(mx, my):
                        current_state = STATE_MENU
                        
                elif current_state == STATE_GAME_OVER:
                    active_game_over_btns = []
                    if not local_rematch_requested and winner_msg not in ["OPPONENT LEFT", "CONNECTION LOST"]:
                        active_game_over_btns.append(game_over_buttons[0]) # Play Again
                    active_game_over_btns.append(game_over_buttons[1]) # Main Menu
                    
                    for btn in active_game_over_btns:
                        res = btn.check_click(mx, my)
                        if res == "PLAY_AGAIN":
                            if current_mode == MODE_LAN:
                                local_rematch_requested = True
                                winner_msg = "WAITING FOR OPPONENT..."
                                if lan_network_manager:
                                    if local_p_id == 1: # We are host, we pick the seed!
                                        next_seed = random.randint(0, 999999)
                                        rematch_seed = next_seed
                                        lan_network_manager.send_message({"type": "rematch", "seed": next_seed})
                                    else:
                                        lan_network_manager.send_message({"type": "rematch"})
                            else:
                                engine.setup_game(create_full_deck())
                                current_state = STATE_DEALING
                                deal_step = 0
                                deal_next_action_ms = sync_now_ms + int(333 * sf)
                                bot = Bot(player_id=2, rating=current_bot_rating) if current_mode == MODE_BOT else None
                                pending_play_intents.clear()
                        elif res == STATE_MENU:
                            if current_mode == MODE_LAN and lan_network_manager:
                                lan_network_manager.send_message({"type": "cancel"})
                            current_state = STATE_MENU
                            if lan_network_manager:
                                lan_network_manager.cancel()
                                lan_network_manager = None
                            local_rematch_requested = False
                            remote_rematch_requested = False

                elif current_state == STATE_BOT_SELECT:
                    if bot_val_rect.collidepoint(mx, my):
                        bot_input_active = True
                        bot_input_text = str(bot_slider.val)
                    else:
                        if bot_input_active:
                            bot_input_active = False
                            if bot_input_text.strip():
                                try:
                                    nv = int(bot_input_text)
                                    nv = int(round(nv / 10.0) * 10)
                                    bot_slider.set_val(nv)
                                except ValueError:
                                    pass
                            bot_input_text = ""

                    res = bot_minus_btn.check_click(mx, my)
                    if res == "MINUS_1": bot_slider.set_val(bot_slider.val - 1)
                    
                    res = bot_plus_btn.check_click(mx, my)
                    if res == "PLUS_1": bot_slider.set_val(bot_slider.val + 1)
                    
                    res = bot_start_btn.check_click(mx, my)
                    if res == "START_BOT":
                        if bot_input_active:
                            bot_input_active = False
                            if bot_input_text.strip():
                                try:
                                    nv = int(bot_input_text)
                                    nv = int(round(nv / 10.0) * 10)
                                    bot_slider.set_val(nv)
                                except ValueError:
                                    pass

                        current_bot_rating = bot_slider.val
                        current_mode = MODE_BOT
                        os.system('cls' if os.name == 'nt' else 'clear')
                        engine.setup_game(create_full_deck())
                        current_state = STATE_DEALING
                        deal_step = 0
                        deal_next_action_ms = sync_now_ms + int(333 * sf)
                        bot = Bot(player_id=2, rating=current_bot_rating)
                        pending_play_intents.clear()
                        
                    res = bot_back_btn.check_click(mx, my)
                    if res == STATE_MENU:
                        current_state = STATE_MENU

                elif current_state == STATE_PLAYING:
                    if stuck_btn.check_click(mx, my):
                        if current_mode == MODE_SINGLE:
                            if engine.verify_board_stuck():
                                engine.stuck_calls[1] = sync_now_ms
                                print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P1 called STUCK.")
                            else:
                                stuck_shake_until_ms = sync_now_ms + 1000 
                        else:
                            if current_mode == MODE_LAN:
                                engine.stuck_calls[local_p_id] = sync_now_ms
                                print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P{local_p_id} called STUCK.")
                                if lan_network_manager:
                                    lan_network_manager.send_message({"type": "stuck", "p_id": local_p_id, "time": sync_now_ms})
                            else:
                                if event.button == 1:
                                    engine.stuck_calls[1] = sync_now_ms
                                    print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P1 called STUCK.")
                                elif event.button == 3:
                                    engine.stuck_calls[2] = sync_now_ms
                                    print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] P2 called STUCK.")
                    elif hovered_card:
                        if event.button == 1 and hovered_pid == local_p_id:
                            t = sync_now_ms
                            if current_mode == MODE_LAN:
                                pending_play_intents.append({
                                    "type": "pickup",
                                    "p_id": local_p_id,
                                    "timestamp": t,
                                    "source": "MOUSE"
                                })
                                if lan_network_manager:
                                    lan_network_manager.send_message({"type": "pickup", "p_id": local_p_id, "time": t})
                            else:
                                pending_play_intents.append({
                                    "type": "pickup",
                                    "p_id": local_p_id,
                                    "timestamp": t,
                                    "source": "MOUSE"
                                })
                        elif event.button == 3 and hovered_pid == remote_p_id and current_mode != MODE_LAN:
                            t = sync_now_ms
                            pending_play_intents.append({
                                "type": "pickup",
                                "p_id": remote_p_id,
                                "timestamp": t,
                                "source": "MOUSE"
                            })
                    else:
                        for i, rect in enumerate(renderer.pile_rects):
                            hitbox = rect.inflate(renderer.Gap, renderer.Gap)
                            if hitbox.collidepoint(event.pos):
                                if current_mode == MODE_LAN:
                                    if event.button == 1: # Left click only in LAN mode for your own player
                                        t = sync_now_ms
                                        pending_play_intents.append({
                                            "type": "play",
                                            "p_id": local_p_id, 
                                            "pile": i, 
                                            "timestamp": t, 
                                            "source": "MOUSE"
                                        })
                                        if lan_network_manager:
                                            lan_network_manager.send_message({"type": "play", "p_id": local_p_id, "pile": i, "time": t})
                                else:
                                    if event.button == 1:
                                        pending_play_intents.append({"type": "play", "p_id": 1, "pile": i, "timestamp": sync_now_ms, "source": "MOUSE"})
                                    elif event.button == 3:
                                        pending_play_intents.append({"type": "play", "p_id": 2, "pile": i, "timestamp": sync_now_ms, "source": "MOUSE"})

        # ---------------------------------------------------------
        # WIN & STUCK RESOLUTION LOGIC
        # ---------------------------------------------------------
        if current_state == STATE_PLAYING and not scheduler.pending_sequence:
            p1_empty = engine.decks[1].is_empty() and len(engine.bumps[1]) == 0
            p2_empty = engine.decks[2].is_empty() and len(engine.bumps[2]) == 0
            
            if p1_empty:
                winner_msg = "YOU WIN!" if current_mode != MODE_LAN else f"PLAYER 1 WINS!"
                current_state = STATE_GAME_OVER
            elif p2_empty:
                winner_msg = "CPU WINS!" if current_mode == MODE_BOT else "PLAYER 2 WINS!"
                current_state = STATE_GAME_OVER
            else:
                trigger_scoop = False
                trigger_time = 0
                
                if current_mode == MODE_SINGLE:
                    if engine.stuck_calls[1] is not None:
                        trigger_scoop = True
                        trigger_time = engine.stuck_calls[1]
                else:
                    if engine.stuck_calls[1] is not None and engine.stuck_calls[2] is not None:
                        trigger_scoop = True
                        trigger_time = max(engine.stuck_calls[1], engine.stuck_calls[2])
                        
                if trigger_scoop:
                    scheduler.schedule("SCOOP", trigger_time + SEQUENCE_START_DELAY_MS)

        # ---------------------------------------------------------
        # RENDERING
        # ---------------------------------------------------------
        if current_state == STATE_MENU:
            for btn in menu_buttons: btn.check_hover(mx, my)
            renderer.render_menu(menu_buttons)
            
        elif current_state == STATE_HELP:
            back_button.check_hover(mx, my)
            renderer.render_help(back_button)
            
        elif current_state == STATE_BOT_SELECT:
            bot_minus_btn.check_hover(mx, my)
            bot_plus_btn.check_hover(mx, my)
            bot_start_btn.check_hover(mx, my)
            bot_back_btn.check_hover(mx, my)
            bot_val_rect = renderer.render_bot_select(bot_slider, bot_minus_btn, bot_plus_btn, bot_start_btn, bot_back_btn, bot_input_active, bot_input_text)
            
        elif current_state in [STATE_MP_MODE_SELECT, STATE_ONLINE_WIP, STATE_LAN_CONNECTING, STATE_LAN_PEER_PICKER, STATE_MATCH_STARTING]:
            btns_to_render = []
            txt_input = None
            
            if current_state == STATE_MP_MODE_SELECT:
                btns_to_render = mp_mode_buttons[:]
                btns_to_render.append(edit_name_btn)
                if show_name_input:
                    txt_input = name_input
            elif current_state == STATE_ONLINE_WIP:
                btns_to_render = wip_buttons
            elif current_state == STATE_LAN_CONNECTING:
                btns_to_render = mp_cancel_btn[:]
                if lan_timed_out:
                    btns_to_render.append(lan_retry_btn)
            elif current_state == STATE_LAN_PEER_PICKER:
                btns_to_render = mp_cancel_btn[:]
                btns_to_render.extend(peer_buttons)
                
            for btn in btns_to_render: btn.check_hover(mx, my)
            
            renderer.render_mp_ui(
                state=current_state,
                buttons=btns_to_render,
                text_input=txt_input,
                player_name=player_name,
                opponent_name=opponent_name,
                peer_list=peer_list,
                lan_timed_out=lan_timed_out,
                lan_status_text=lan_status_text,
                show_debug=show_debug
            )
            
        elif current_state == STATE_GAME_OVER:
            renderer.render_game(engine, bot, current_mode, show_debug, sync_now_ms, local_p_id, remote_p_id, opponent_name, dev_btns)
            
            active_game_over_btns = []
            if not local_rematch_requested and winner_msg not in ["OPPONENT LEFT", "CONNECTION LOST"]:
                active_game_over_btns.append(game_over_buttons[0])
            active_game_over_btns.append(game_over_buttons[1])
            
            for btn in active_game_over_btns: btn.check_hover(mx, my)
            renderer.render_game_over(winner_msg, active_game_over_btns)
            
        elif current_state == STATE_DEALING:
            if sync_now_ms >= deal_next_action_ms:
                if deal_step < 4:
                    for d, deck, start_pos in [(deal_step, engine.decks[2], renderer.DeckP2_Pos), (deal_step + 4, engine.decks[1], renderer.DeckP1_Pos)]:
                        if not deck.is_empty():
                            c = deck.pop_top()
                            engine.piles[d].append(c)
                            c.start_animation(start_pos, renderer.pile_rects[d].topleft, sync_now_ms, duration_ms=int(333*sf), flip=True)
                    deal_step += 1
                    deal_next_action_ms = sync_now_ms + int(250 * sf)
                else:
                    animating = any(pile and pile[-1].is_animating for pile in engine.piles)
                    if not animating:
                        current_state = STATE_PLAYING
                        match_start_time = sync_now_ms
                        print(f"{fmt_time(sync_now_ms, match_start_time)} [SYS] MATCH STARTED!")
                        
            renderer.render_game(engine, bot, current_mode, show_debug, sync_now_ms, local_p_id, remote_p_id, opponent_name, dev_btns)
            
        elif current_state == STATE_SCOOPING:
            if scoop_manager.update(sync_now_ms, sf=sf) == "DONE":
                engine.execute_scoop_finish(scoop_manager.cards, scoop_manager.cpu_cards)
                current_state = STATE_DEALING
                deal_step = 0
                deal_next_action_ms = sync_now_ms + int(333 * sf)
                pending_play_intents.clear()
                
            renderer.render_game(engine, bot, current_mode, show_debug, sync_now_ms, local_p_id, remote_p_id, opponent_name, dev_btns)
            
            def draw_scoop_card(c):
                dummy_rect = pygame.Rect(
                    int(c.current_pos[0] - c.skew_offset[0]), 
                    int(c.current_pos[1] - c.skew_offset[1]), 
                    renderer.CardW, renderer.CardH
                )
                renderer.draw_card(screen, c, dummy_rect, sync_now_ms, face_up=c.face_up)
                
            for i in scoop_manager.launched_piles:
                for c in scoop_manager.piles_data[i]: draw_scoop_card(c)
            for c in reversed(scoop_manager.cpu_cards): draw_scoop_card(c)
            for c in reversed(scoop_manager.cards): draw_scoop_card(c)
                
        elif current_state == STATE_PLAYING:
            stuck_btn.check_hover(mx, my)
            for btn in dev_btns: btn.check_hover(mx, my)
            renderer.render_game(engine, bot, current_mode, show_debug, sync_now_ms, local_p_id, remote_p_id, opponent_name, dev_btns)
            
            draw_x, draw_y = stuck_btn.rect.x, stuck_btn.rect.y
            
            bg_c = (150, 100, 50)
            if current_mode != MODE_SINGLE:
                if engine.stuck_calls[1] is not None and engine.stuck_calls[2] is not None:
                    bg_c = (200, 200, 50)
                elif engine.stuck_calls[1] is not None:
                    bg_c = (200, 150, 50)
                elif engine.stuck_calls[2] is not None:
                    bg_c = (150, 200, 50)

            if stuck_shake_until_ms > sync_now_ms:
                draw_x += random.randint(-5, 5)
                draw_y += random.randint(-5, 5)
                bg_c = ERROR_COLOR
                
            shaking_rect = pygame.Rect(draw_x, draw_y, stuck_btn.rect.w, stuck_btn.rect.h)
            pygame.draw.rect(screen, bg_c, shaking_rect, border_radius=8)
            pygame.draw.rect(screen, (255,255,255), shaking_rect, 2, border_radius=8)
            
            wait_text = "STUCK"
            if current_mode != MODE_SINGLE and (engine.stuck_calls[1] is not None or engine.stuck_calls[2] is not None):
                wait_text = "WAITING..."
            bt = renderer.font.render(wait_text, True, (255,255,255))
            screen.blit(bt, bt.get_rect(center=shaking_rect.center))

        if show_debug:
            slowmo_btn.check_hover(mx, my)
            slowmo_btn.draw(screen, slowmo_font)

        pygame.display.flip()
        clock.tick(FPS)

    if lan_network_manager:
        lan_network_manager.cancel()

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()