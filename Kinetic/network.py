# network.py
import socket
import threading
import queue
import json
import time
import uuid
import random
from config import (
    LAN_DISCOVERY_PORT, LAN_GAME_PORT, LAN_BROADCAST_INTERVAL_MS,
    LAN_DISCOVERY_TIMEOUT_MS, LAN_MULTI_PEER_WINDOW_MS
)

class NetworkManager:
    def __init__(self, player_name: str):
        self.player_name = player_name
        self.session_id = uuid.uuid4().hex
        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self._sockets = []
        self.conn = None

    def start(self):
        self.cancel()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def connect_to_peer(self, ip: str):
        self.cancel()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_connect, args=(ip,), daemon=True)
        self.thread.start()

    def cancel(self):
        self.stop_event.set()
        for sock in self._sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass
        self._sockets.clear()
        self.conn = None
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.5)

    def poll_events(self) -> list[dict]:
        events = []
        while not self.q.empty():
            events.append(self.q.get())
        return events

    def send_message(self, msg_dict):
        if self.conn:
            try:
                # The \n is the glue-breaker!
                payload = json.dumps(msg_dict) + "\n"
                self.conn.sendall(payload.encode('utf-8'))
            except Exception:
                self.q.put({"type": "DISCONNECT"})
                self.cancel()

    def _register_sock(self, sock):
        self._sockets.append(sock)
        return sock

    def _recv_loop(self, sock, f):
        try:
            while not self.stop_event.is_set():
                line = f.readline()
                if not line:
                    break
                self.q.put({"type": "NET_MSG", "data": json.loads(line)})
        except Exception:
            pass
        finally:
            if not self.stop_event.is_set():
                self.q.put({"type": "DISCONNECT"})
            self.cancel()

    def _handshake_client(self, sock):
        try:
            # Step 1: Cristian's Alg (Note Start Time)
            t_start = time.time() * 1000
            msg = json.dumps({"type": "hello", "name": self.player_name, "t_start": t_start}) + "\n"
            sock.sendall(msg.encode('utf-8'))
            
            f = sock.makefile('r', encoding='utf-8')
            line = f.readline()
            if not line: return None, 0, 0
            data = json.loads(line)
            
            # Step 2: Note End Time & Calculate Offset
            t_end = time.time() * 1000
            t_host = data.get("t_host", t_end)
            latency = (t_end - t_start) / 2.0
            offset = t_host + latency - t_end
            
            return data.get("name", "Unknown"), offset, data.get("seed", 0)
        except Exception:
            return None, 0, 0

    def _handshake_host(self, sock):
        try:
            f = sock.makefile('r', encoding='utf-8')
            line = f.readline()
            if not line: return None, 0, 0
            data = json.loads(line)
            
            t_host = time.time() * 1000
            seed = random.randint(0, 999999) # Send the deck shuffle seed!
            msg = json.dumps({"type": "hello", "name": self.player_name, "t_host": t_host, "seed": seed}) + "\n"
            sock.sendall(msg.encode('utf-8'))
            
            return data.get("name", "Unknown"), 0, seed
        except Exception:
            return None, 0, 0

    def _run_connect(self, ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._register_sock(sock)
        sock.settimeout(2.0)
        try:
            sock.connect((ip, LAN_GAME_PORT))
            # DO NOT clear timeout here - let the handshake use the 2.0s limit!
            opponent_name, offset, seed = self._handshake_client(sock)
            if opponent_name and not self.stop_event.is_set():
                sock.settimeout(None) # Restore blocking for main game loop
                self.conn = sock
                self.q.put({"type": "CONNECTED", "opponent_name": opponent_name, "is_host": False, "offset": offset, "seed": seed})
                f = sock.makefile('r', encoding='utf-8')
                self._recv_loop(sock, f)
        except Exception:
            if not self.stop_event.is_set():
                self.q.put({"type": "TIMEOUT"})
        finally:
            if self.stop_event.is_set():
                sock.close()

    def _run(self):
        # 1. EVERYONE opens a TCP listener (Everyone can host)
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._register_sock(server_sock)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_sock.bind(('', LAN_GAME_PORT))
            server_sock.listen(5)
            server_sock.settimeout(0.1) 
        except Exception:
            server_sock = None

        # 2. EVERYONE opens a UDP listener and broadcaster
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._register_sock(udp_sock)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            udp_sock.bind(('', LAN_DISCOVERY_PORT))
        except Exception:
            pass
        udp_sock.settimeout(0.1)

        start_time = time.time()
        last_broadcast = 0
        discovered_hosts = {} 
        first_discovery_time = None

        while not self.stop_event.is_set():
            now = time.time()
            elapsed_time = now - start_time
            
            self.q.put({"type": "DISCOVERING", "elapsed": elapsed_time})

            # Hardened Accept: Only accept incoming connections AFTER the UDP window has completely finished.
            if server_sock and (elapsed_time >= LAN_MULTI_PEER_WINDOW_MS / 1000.0):
                try:
                    conn, addr = server_sock.accept()
                    self._register_sock(conn)
                    conn.settimeout(2.0) # Apply strict 2-second timeout for ghost-ping handshakes
                    opponent_name, offset, seed = self._handshake_host(conn)
                    
                    if opponent_name and not self.stop_event.is_set():
                        conn.settimeout(None) # Handshake passed, restore to infinite timeout for game loop
                        self.conn = conn
                        self.q.put({"type": "CONNECTED", "opponent_name": opponent_name, "is_host": True, "offset": offset, "seed": seed})
                        f = conn.makefile('r', encoding='utf-8')
                        self._recv_loop(conn, f)
                        break # Only stop discovering if we ACTUALLY connected!
                    else:
                        # Handshake failed or ghost ping. Clean up the bad socket and keep searching.
                        try:
                            conn.close()
                            if conn in self._sockets:
                                self._sockets.remove(conn)
                        except Exception:
                            pass
                except socket.timeout:
                    pass
                except Exception:
                    pass

            if now - last_broadcast >= LAN_BROADCAST_INTERVAL_MS / 1000.0:
                payload = json.dumps({"type": "kinetic_discover", "name": self.player_name, "session": self.session_id}).encode('utf-8')
                try:
                    udp_sock.sendto(payload, ('<broadcast>', LAN_DISCOVERY_PORT))
                except Exception:
                    pass
                last_broadcast = now

            try:
                data, addr = udp_sock.recvfrom(1024)
                msg = json.loads(data.decode('utf-8'))
                
                if msg.get("type") == "kinetic_discover" and msg.get("session") != self.session_id:
                    ip = addr[0]
                    if ip not in discovered_hosts:
                        discovered_hosts[ip] = {
                            "name": msg.get("name", "Unknown"),
                            "session": msg.get("session")
                        }
                        if first_discovery_time is None:
                            first_discovery_time = now
            except socket.timeout:
                pass
            except Exception:
                pass

            if first_discovery_time and (now - first_discovery_time >= LAN_MULTI_PEER_WINDOW_MS / 1000.0):
                if len(discovered_hosts) == 1:
                    ip, peer_data = list(discovered_hosts.items())[0]
                    # THE TIE BREAKER: Lower Session ID yields and connects as Client
                    if self.session_id < peer_data["session"]:
                        time.sleep(0.5) 
                        self._run_connect(ip)
                        break
                    elif self.session_id == peer_data["session"]:
                        # Collision detected! Regenerate session ID to break the tie and try again.
                        self.session_id = uuid.uuid4().hex
                        discovered_hosts.clear()
                        first_discovery_time = None
                    else:
                        discovered_hosts.clear()
                        first_discovery_time = None
                elif len(discovered_hosts) > 1:
                    peers = [{"name": data["name"], "ip": ip} for ip, data in discovered_hosts.items()]
                    self.q.put({"type": "MULTIPLE_FOUND", "peers": peers})
                    break 

            if not first_discovery_time and (now - start_time >= LAN_DISCOVERY_TIMEOUT_MS / 1000.0):
                self.q.put({"type": "TIMEOUT"})
                break