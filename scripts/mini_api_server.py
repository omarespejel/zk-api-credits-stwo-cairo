#!/usr/bin/env python3
"""Minimal demo verification endpoint for RLN-like API-credits flow."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from rln_math import Share, parse_share, recover_identity_secret, to_felt_hex


def find_cairo_prove(explicit: str | None) -> str:
    if explicit:
        return explicit

    import shutil

    candidate = shutil.which("cairo-prove")
    if candidate:
        return candidate
    raise RuntimeError("cairo-prove not found in PATH. Set --cairo-prove.")


class ServerState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.spent: dict[str, tuple[int, int, int]] = {}


state = ServerState()


def run_verify(cairo_prove: str, proof_path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [cairo_prove, "verify", str(proof_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    ok = proc.returncode == 0
    output = proc.stdout.strip() + "\n" + proc.stderr.strip()
    return ok, output.strip()


def slash_payload(share1: Share, share2: Share) -> dict:
    identity_secret = recover_identity_secret(share1.x, share1.y, share2.x, share2.y)
    return {
        "slash": True,
        "nullifier": to_felt_hex(share1.nullifier),
        "ticket_index": to_felt_hex(share1.ticket_index),
        "recovered_identity_secret": to_felt_hex(identity_secret),
        "shares": [
            {"x": to_felt_hex(share1.x), "y": to_felt_hex(share1.y)},
            {"x": to_felt_hex(share2.x), "y": to_felt_hex(share2.y)},
        ],
    }


def safe_temp_file(data: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="proof_", dir=tempfile.gettempdir())
    with open(fd, "w") as f:
        f.write(data)
    return Path(path)


class RequestHandler(BaseHTTPRequestHandler):
    cairo_prove: str
    server_state: ServerState

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_POST(self) -> None:
        if self.path != "/submit":
            self._json(404, {"error": "not found"})
            return

        try:
            payload = self._parse_body()
        except Exception as exc:
            self._json(400, {"error": f"invalid json: {exc}"})
            return

        try:
            share = parse_share(payload)
        except Exception as exc:
            self._json(400, {"error": f"invalid share: {exc}"})
            return

        proof_data = payload.get("proof_b64")
        proof_path = payload.get("proof_path")

        if proof_path is None and proof_data is None:
            self._json(400, {"error": "provide proof_path or proof_b64"})
            return

        temp_path: Path | None = None
        try:
            if proof_path is not None:
                proof_file = Path(str(proof_path))
                if not proof_file.exists():
                    self._json(400, {"error": f"proof_path not found: {proof_path}"})
                    return
            else:
                raw = base64.b64decode(proof_data, validate=True)
                temp_path = safe_temp_file(raw.decode("utf-8"))
                proof_file = temp_path

            verified, verifier_output = run_verify(self.cairo_prove, proof_file)
            if not verified:
                self._json(
                    400,
                    {"error": "proof verify failed", "verifier_output": verifier_output},
                )
                return
        except Exception as exc:
            self._json(500, {"error": f"verification error: {exc}"})
            return
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass

        key = to_felt_hex(share.nullifier)
        with self.server_state.lock:
            previous = self.server_state.spent.get(key)
            if previous is None:
                self.server_state.spent[key] = (share.ticket_index, share.x, share.y)
                self._json(
                    200,
                    {
                        "status": "accepted",
                        "nullifier": key,
                        "ticket_index": to_felt_hex(share.ticket_index),
                        "x": to_felt_hex(share.x),
                    },
                )
                return

            prev_ticket, prev_x, prev_y = previous
            if prev_ticket != share.ticket_index:
                self._json(
                    409,
                    {
                        "error": "nullifier replay with different ticket_index",
                        "previous": {
                            "ticket_index": to_felt_hex(prev_ticket),
                            "x": to_felt_hex(prev_x),
                            "y": to_felt_hex(prev_y),
                        },
                    },
                )
                return
            if prev_x == share.x:
                if prev_y == share.y:
                    self._json(200, {"status": "replay_same_share", "nullifier": key})
                    return
                self._json(409, {"error": "same x, inconsistent y"})
                return

            second_share = Share(
                nullifier=share.nullifier,
                ticket_index=share.ticket_index,
                x=prev_x,
                y=prev_y,
            )
            payload = slash_payload(share, second_share)
            payload["status"] = "slashed"
            self._json(409, payload)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/state":
            with self.server_state.lock:
                body = {
                    "active_spent": {
                        k: {
                            "ticket_index": to_felt_hex(v[0]),
                            "x": to_felt_hex(v[1]),
                            "y": to_felt_hex(v[2]),
                        }
                        for k, v in self.server_state.spent.items()
                    }
                }
            self._json(200, body)
            return
        self._json(404, {"error": "not found"})


def run_server(host: str, port: int, cairo_prove: str) -> None:
    handler = RequestHandler
    handler.cairo_prove = cairo_prove
    handler.server_state = state
    server = HTTPServer((host, port), handler)
    print(f"Listening on http://{host}:{port}")
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cairo-prove", dest="cairo_prove", default=None)
    args = parser.parse_args()

    cairo_prove = find_cairo_prove(args.cairo_prove)
    run_server(args.host, args.port, cairo_prove)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
