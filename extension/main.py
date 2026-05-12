"""
Extension — Entry point for the local graph management server.

Usage:
    python main.py                  # Start on default port 8100
    python main.py --port 8200      # Custom port
    python main.py --host 0.0.0.0   # Bind to all interfaces
"""
import argparse
import logging
import sys

import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="Code Review Graph Extension — Local server for graph management"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8100,
        help="Port to listen on (default: 8100)",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development",
    )
    args = parser.parse_args()

    print(f"""
+==================================================+
|   Code Review Graph Extension                    |
|   Local server for graph-powered code review     |
+==================================================+
|   Host: {args.host:<40s}|
|   Port: {args.port:<40d}|
|   Docs: http://{args.host}:{args.port}/docs{' ' * (25 - len(str(args.port)))}|
+==================================================+
    """)

    uvicorn.run(
        "api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
