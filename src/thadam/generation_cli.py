"""CLI translation for provider connections, proposals and explicit review/save."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
import webbrowser
from pathlib import Path

from thadam._json import read_json
from thadam.generation import (
    INSTRUCTIONS,
    load_draft,
    publish_draft,
    review_candidate,
    selected_suite,
    suggest_cases,
    validate_request,
    write_draft,
)
from thadam.suite_writing import file_fingerprint


def add_generation_commands(commands):
    auth = commands.add_parser(
        "auth",
        help="Connect ChatGPT subscription or your OpenAI API key",
        description="Connections are stored privately for your local user, outside projects.",
    )
    auth.add_argument("action", choices=("status", "login", "api-key", "disconnect", "models"))
    auth.add_argument("--connection", choices=("chatgpt", "api_key"))
    auth.add_argument("--no-browser", action="store_true")
    suggest = commands.add_parser(
        "suggest",
        help="Preview context or explicitly generate scenario drafts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples\n  thadam suggest context.json\n  thadam auth login\n  thadam auth models --connection chatgpt\n  thadam suggest context.json --connection chatgpt --model MODEL --draft drafts/cases.json --send\n\nWithout --send, this only previews context. Nothing executes your agent.\nExit codes: 0 success; 2 invalid input or provider failure.",
    )
    suggest.add_argument("context", type=Path)
    suggest.add_argument("--connection", choices=("chatgpt", "api_key"))
    suggest.add_argument("--model")
    suggest.add_argument("--draft", type=Path)
    suggest.add_argument(
        "--source",
        type=Path,
        help="Existing suite to append reviewed cases to; not automatically sent as context",
    )
    suggest.add_argument(
        "--send",
        action="store_true",
        help="Explicitly send the previewed context to the selected provider",
    )
    review = commands.add_parser(
        "review-draft", help="Review/edit one proposed case; never modify a runnable suite"
    )
    review.add_argument("draft", type=Path)
    review.add_argument("--case", type=int, required=True, help="Suggestion number, starting at 1")
    review.add_argument("--decision", required=True, choices=("pending", "accepted", "discarded"))
    review.add_argument("--case-json", type=Path, help="Edited {id,input,assertions} JSON")
    save = commands.add_parser(
        "save-draft", help="Preview or explicitly save accepted cases into a suite"
    )
    save.add_argument("draft", type=Path)
    save.add_argument("--destination", type=Path, required=True)
    save.add_argument("--suite-id")
    save.add_argument("--revision")
    save.add_argument(
        "--write",
        action="store_true",
        help="Save the previewed suite; no evaluation or baseline approval",
    )
    return (auth, suggest, review, save)


def handle_generation_command(args) -> int:
    """Translate explicit arguments; SDK owns validation and save behavior."""
    try:
        if args.command == "auth":
            from thadam.providers.credentials import CredentialStore
            from thadam.providers.openai import connect_api_key, connection_status, list_models

            store = CredentialStore()
            if args.action == "status":
                print(json.dumps(connection_status(store), indent=2))
            elif args.action == "api-key":
                connect_api_key(getpass.getpass("OpenAI API key (hidden): "), store)
                print("API-key connection saved privately. Generation uses your API billing.")
            elif args.action == "disconnect":
                if not args.connection:
                    raise ValueError("Choose --connection chatgpt or api_key")
                store.disconnect(args.connection)
                print(
                    "Saved connection removed. Environment-provided API keys must be unset separately. You can also revoke app access in ChatGPT settings."
                )
            elif args.action == "models":
                if not args.connection:
                    raise ValueError("Choose --connection chatgpt or api_key")
                print(json.dumps(list_models(args.connection, store=store), indent=2))
            else:
                from thadam.providers.chatgpt_auth import ChatGPTSignIn

                signin = ChatGPTSignIn(store)
                try:
                    url = signin.start()
                    print("Authorize ChatGPT plan usage in your browser:\n" + url)
                    if not args.no_browser:
                        webbrowser.open(url)
                    while signin.status()["state"] == "pending":
                        time.sleep(0.1)
                    status = signin.status()
                    if status["state"] != "connected" or status["error"]:
                        raise ValueError(status["error"] or "Sign-in did not complete")
                    print("ChatGPT connected. Eligible generation uses your plan allowance.")
                finally:
                    signin.close()
        elif args.command == "suggest":
            from thadam.providers.openai import OpenAIProvider

            request = validate_request(read_json(args.context))
            if not args.send:
                print(
                    json.dumps(
                        {"instructions": INSTRUCTIONS, "context": request},
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                print(
                    "Preview only. Use --connection, --model, --draft and --send to generate.",
                    file=sys.stderr,
                )
                return 0
            if not args.connection or not args.model or not args.draft:
                raise ValueError("Generation requires --connection, --model, --draft and --send")
            if args.draft.exists():
                raise ValueError("Choose a new draft path; existing evidence is preserved")
            source = None
            if args.source:
                from thadam.suites import suite_from_dict

                before = file_fingerprint(args.source)
                data = read_json(args.source)
                suite_from_dict(data)
                if file_fingerprint(args.source) != before:
                    raise ValueError("Source suite changed while loading")
                source = {"path": str(args.source.resolve()), "fingerprint": before, "data": data}
            result = suggest_cases(
                OpenAIProvider(connection=args.connection, model=args.model), request, source=source
            )
            write_draft(result, args.draft)
            print(f"Saved {len(result['candidates'])} unreviewed suggestions to {args.draft}")
        else:
            before = file_fingerprint(args.draft)
            draft = load_draft(args.draft)
            if file_fingerprint(args.draft) != before:
                raise ValueError("Draft changed while loading; try again")
            if args.command == "review-draft":
                edited = read_json(args.case_json) if args.case_json else None
                result = review_candidate(draft, args.case - 1, decision=args.decision, case=edited)
                write_draft(result, args.draft, expected_fingerprint=before)
                print(f"Suggestion {args.case}: {args.decision}. Runnable suites are unchanged.")
            else:
                data = selected_suite(draft, suite_id=args.suite_id, revision=args.revision)
                if not args.write:
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                    print("Preview only. Add --write to save this suite.", file=sys.stderr)
                    return 0
                source = draft["source"]
                if source and file_fingerprint(source["path"]) != source["fingerprint"]:
                    raise ValueError("Source suite changed; generate a fresh draft")
                expected = (
                    source["fingerprint"]
                    if source and Path(source["path"]).resolve() == args.destination.resolve()
                    else None
                )
                if file_fingerprint(args.draft) != before:
                    raise ValueError("Draft changed since preview")
                publish_draft(
                    draft,
                    args.destination,
                    suite_id=args.suite_id,
                    revision=args.revision,
                    expected_fingerprint=expected,
                )
                print(f"Reviewed suite saved to {args.destination}. Run it explicitly when ready.")
        return 0
    except (ValueError, OSError) as error:
        from thadam.terminal import display_text

        print("thadam: " + display_text(str(error)), file=sys.stderr)
        return 2
