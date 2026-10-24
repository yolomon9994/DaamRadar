"""Run with: python -m config.serve --host 127.0.0.1 --port 8080."""
import argparse
import ipaddress
import os
from pathlib import Path

from dotenv import load_dotenv


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be a positive integer.")
    return number


def proxy_ip(value):
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise argparse.ArgumentTypeError("Use the exact trusted proxy IP address.") from None


def main(argv=None):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    parser = argparse.ArgumentParser(description="Serve DaamRadar using Waitress and production settings.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=positive_int, default=os.getenv("PORT", "8080"))
    parser.add_argument("--threads", type=positive_int, default="4")
    parser.add_argument("--trusted-proxy", type=proxy_ip, default=os.getenv("WAITRESS_TRUSTED_PROXY") or None)
    args = parser.parse_args(argv)
    if args.port > 65535:
        parser.error("Port must be between 1 and 65535.")
    # This entry point always uses the production profile, even in a CI shell.
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.production"
    from django.core.wsgi import get_wsgi_application
    from waitress import serve

    application = get_wsgi_application()
    options = {"host": args.host, "port": args.port, "threads": args.threads,
               "clear_untrusted_proxy_headers": True, "expose_tracebacks": False}
    if args.trusted_proxy:
        options.update(trusted_proxy=args.trusted_proxy, trusted_proxy_count=1,
                       trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for"})
    serve(application, **options)


if __name__ == "__main__":
    main()
