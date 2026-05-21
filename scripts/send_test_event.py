"""Send a test event to a running server."""
import sys

import httpx


def main() -> None:
    event_type = sys.argv[1] if len(sys.argv) > 1 else "ORDER_PLACED"
    payload = {
        "order_id": 1001,
        "user_phone": "+919876543210",
        "event_type": event_type,
    }
    r = httpx.post("http://localhost:8000/event/", json=payload, timeout=10)
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()


