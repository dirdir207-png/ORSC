"""macOS entrypoint for the loopback-only Crew session broker."""

import argparse
from pathlib import Path

from crew.broker import BrokerConfig, create_broker_app
from crew.mac_secrets import MacKeychainKeyProvider, load_or_create_capability
from crew.session_credentials import SessionCipher, SessionCredentialStore
from crew.transports import SessionCookieTransport

HEALTH_QUERY = "query CrewConnectionHealth { currentUser { id } }"
CURRENT_USER_QUERY = """ query CurrentUser { currentUser { accounts { id displayName } } } """
TRANSFER_MUTATION = """ mutation InitiateTransferScottie($input: InitiateTransferInput!) { initiateTransfer(input: $input) { result { id __typename } __typename } } """
DEFAULT_OPERATION_DOCUMENTS = {
    "CrewConnectionHealth": (HEALTH_QUERY, False),
    "CurrentUser": (CURRENT_USER_QUERY, False),
    "InitiateTransferScottie": (TRANSFER_MUTATION, True),
}
DEFAULT_OPERATIONS = frozenset(DEFAULT_OPERATION_DOCUMENTS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the SimpleCrew Crew session broker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--capability-file", type=Path)
    return parser


def parse_args(argv=None, *, home: Path | None = None):
    args = build_parser().parse_args(argv)
    try:
        BrokerConfig.validate_bind_host(args.host)
    except ValueError as exc:
        build_parser().error(str(exc))
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    base = args.data_dir or (home or Path.home()) / "Library/Application Support/SimpleCrew"
    args.data_dir = base
    args.database = args.database or base / "simplecrew.db"
    args.capability_file = args.capability_file or base / "crew-broker.capability"
    return args


def create_app(args):
    args.data_dir.mkdir(parents=True, exist_ok=True)
    store = SessionCredentialStore(
        str(args.database), SessionCipher(MacKeychainKeyProvider())
    )
    capability = load_or_create_capability(args.capability_file)
    transport = SessionCookieTransport(store.load)
    return create_broker_app(BrokerConfig(
        capability=capability,
        credential_store=store,
        transport=transport,
        allowed_operations=DEFAULT_OPERATIONS,
        operation_documents=DEFAULT_OPERATION_DOCUMENTS,
        capturer_factory=__import__("crew.browser_capture", fromlist=["PlaywrightSessionCapturer"]).PlaywrightSessionCapturer,
    ))


def main(argv=None) -> int:
    args = parse_args(argv)
    BrokerConfig.validate_bind_host(args.host)
    app = create_app(args)
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
