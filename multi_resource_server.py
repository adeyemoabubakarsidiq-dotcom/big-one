"""Multi-resource in-memory HTTP API.
Methods: GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE Resources: items, orders """

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import uuid4

ITEMS: dict[str, dict[str, Any]] = {}
ORDERS: dict[str, dict[str, Any]] = {}


class MultiResourceHandler(BaseHTTPRequestHandler):
    server_version = "MultiResource/0.2"

    def _path(self) -> str:
        return self.path.split("?", 1)[0]

    def _normalized_path(self) -> str:
        path = self._path().rstrip("/")
        return path or "/"

    def _match(self, pattern: str) -> re.Match[str] | None:
        return re.fullmatch(pattern, self._normalized_path())

    def _read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _send(self, status: int, payload: Any | None = None, *, head_only: bool = False) -> None:
        if payload is None:
            body = b""
        else:
            body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
        else:
            self.send_header("Content-Length", "0")
        self.end_headers()
        if body and not head_only:
            self.wfile.write(body)

    def _send_allow(self, methods: str) -> None:
        self.send_response(204)
        self.send_header("Allow", methods)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        if self._match(r"/items"):
            return self._send_allow("GET, HEAD, POST, OPTIONS")
        if self._match(r"/items/([^/]+)"):
            return self._send_allow("GET, HEAD, PUT, PATCH, DELETE, OPTIONS")
        if self._match(r"/orders"):
            return self._send_allow("GET, HEAD, POST, OPTIONS")
        if self._match(r"/orders/([^/]+)"):
            return self._send_allow("GET, HEAD, DELETE, OPTIONS")
        if self._path() == "/health":
            return self._send_allow("GET, HEAD, OPTIONS")
        self._send(404, {"error": "not_found", "path": self.path})

    def do_HEAD(self) -> None:
        if self._path() == "/health":
            return self._send(200, {"status": "ok"}, head_only=True)
        if self._match(r"/items"):
            return self._send(200, list(ITEMS.values()), head_only=True)
        m = self._match(r"/items/([^/]+)")
        if m:
            item = ITEMS.get(m.group(1))
            if item:
                return self._send(200, item, head_only=True)
            return self._send(404, {"error": "not_found"}, head_only=True)
        if self._match(r"/orders"):
            return self._send(200, list(ORDERS.values()), head_only=True)
        m = self._match(r"/orders/([^/]+)")
        if m:
            order = ORDERS.get(m.group(1))
            if order:
                return self._send(200, order, head_only=True)
            return self._send(404, {"error": "not_found"}, head_only=True)
        self._send(404, {"error": "not_found", "path": self.path}, head_only=True)

    def do_GET(self) -> None:
        if self._path() == "/health":
            return self._send(200, {"status": "ok"})
        if self._match(r"/items"):
            return self._send(200, list(ITEMS.values()))
        m = self._match(r"/items/([^/]+)")
        if m:
            item = ITEMS.get(m.group(1))
            return self._send(200, item) if item else self._send(404, {"error": "not_found"})
        if self._match(r"/orders"):
            return self._send(200, list(ORDERS.values()))
        m = self._match(r"/orders/([^/]+)")
        if m:
            order = ORDERS.get(m.group(1))
            return self._send(200, order) if order else self._send(404, {"error": "not_found"})
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:
        data = self._read_json()
        if data is None:
            return self._send(400, {"error": "invalid_json"})
        if self._match(r"/items"):
            name, price = data.get("name"), data.get("price")
            if not isinstance(name, str) or not isinstance(price, (int, float)):
                return self._send(400, {"error": "name:str and price:number required"})
            item_id = str(uuid4())[:8]
            item = {"id": item_id, "name": name, "price": float(price)}
            ITEMS[item_id] = item
            return self._send(201, item)
        if self._match(r"/orders"):
            item_id, qty = data.get("item_id"), data.get("qty")
            if item_id not in ITEMS:
                return self._send(400, {"error": "unknown item_id"})
            if not isinstance(qty, int) or qty < 1:
                return self._send(400, {"error": "qty must be positive int"})
            order_id = str(uuid4())[:8]
            order = {"id": order_id, "item_id": item_id, "qty": qty}
            ORDERS[order_id] = order
            return self._send(201, order)
        self._send(404, {"error": "not_found", "path": self.path})

    def do_PUT(self) -> None:
        data = self._read_json()
        if data is None:
            return self._send(400, {"error": "invalid_json"})
        m = self._match(r"/items/([^/]+)")
        if not m:
            return self._send(404, {"error": "not_found", "path": self.path})
        item_id = m.group(1)
        if item_id not in ITEMS:
            return self._send(404, {"error": "not_found"})
        name, price = data.get("name"), data.get("price")
        if not isinstance(name, str) or not isinstance(price, (int, float)):
            return self._send(400, {"error": "name:str and price:number required"})
        item = {"id": item_id, "name": name, "price": float(price)}
        ITEMS[item_id] = item
        self._send(200, item)

    def do_PATCH(self) -> None:
        data = self._read_json()
        if data is None:
            return self._send(400, {"error": "invalid_json"})
        if not data:
            return self._send(400, {"error": "empty patch; send at least one field"})
        m = self._match(r"/items/([^/]+)")
        if not m:
            return self._send(404, {"error": "not_found", "path": self.path})
        item_id = m.group(1)
        if item_id not in ITEMS:
            return self._send(404, {"error": "not_found"})
        item = dict(ITEMS[item_id])
        if "name" in data:
            if not isinstance(data["name"], str):
                return self._send(400, {"error": "name must be str"})
            item["name"] = data["name"]
        if "price" in data:
            if not isinstance(data["price"], (int, float)):
                return self._send(400, {"error": "price must be number"})
            item["price"] = float(data["price"])
        ITEMS[item_id] = item
        self._send(200, item)

    def do_DELETE(self) -> None:
        m = self._match(r"/items/([^/]+)")
        if m:
            item_id = m.group(1)
            if item_id not in ITEMS:
                return self._send(404, {"error": "not_found"})
            del ITEMS[item_id]
            return self._send(204)
        m = self._match(r"/orders/([^/]+)")
        if m:
            order_id = m.group(1)
            if order_id not in ORDERS:
                return self._send(404, {"error": "not_found"})
            del ORDERS[order_id]
            return self._send(204)
        self._send(404, {"error": "not_found", "path": self.path})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.command} {self.path}")


def main() -> None:
    host, port = "127.0.0.1", 8000
    server = HTTPServer((host, port), MultiResourceHandler)
    print(f"Multi-resource API on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye")
        server.server_close()


if __name__ == "__main__":
    main()