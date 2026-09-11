"""
Bare-Metal CLI Runner for Software Factory.
Commands:
  sf audit   --pre <pre_file> --post <post_file> (or git diff)
  sf verify  --repo <repo_dir> [--manifest <manifest.json>]
  sf run     --spec <spec.md> --repo <repo_dir>
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from .governance import GovernanceEngine, DoorType, RiskCategory
from .zero_trust import ZeroTrustGate, BaselineHashGuard

# Terminal ANSI color constants
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"


def format_header(title: str) -> str:
    line = "=" * 68
    return f"{CYAN}{line}\n{BOLD}{title.center(68)}{RESET}\n{CYAN}{line}{RESET}"


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit source modifications via Unity Semantic Delta and Governance Matrix."""
    print(format_header("SOFTWARE FACTORY :: SEMANTIC DELTA & GOVERNANCE AUDIT"))

    if not args.pre or not args.post:
        print(f"{RED}Error: --pre and --post file arguments are required for semantic audit.{RESET}")
        return 1

    pre_path = Path(args.pre)
    post_path = Path(args.post)

    if not pre_path.exists():
        print(f"{RED}Error: Pre-change file '{pre_path}' does not exist.{RESET}")
        return 1
    if not post_path.exists():
        print(f"{RED}Error: Post-change file '{post_path}' does not exist.{RESET}")
        return 1

    engine = GovernanceEngine()
    report = engine.audit_source_pair(pre_path, post_path)

    print(f"\n{BOLD}Audit Target:{RESET} {pre_path.name} -> {post_path.name}")
    print(f"{BOLD}Classification:{RESET} ", end="")
    if report.door_type == DoorType.ONE_WAY:
        print(f"{RED}{BOLD}ONE-WAY DOOR (Requires Socratic Alignment & Ratified ADR){RESET}")
    else:
        print(f"{GREEN}{BOLD}TWO-WAY DOOR (Autonomous Execution Permitted){RESET}")

    # Display Semantic Delta summary if available
    if report.semantic_delta:
        delta = report.semantic_delta
        print(f"\n{CYAN}--- Canonical Semantic Delta (ΔS) ---{RESET}")
        if delta.is_identical:
            print(f"  {GREEN}No semantic changes detected. Structural parity preserved.{RESET}")
        else:
            if delta.added_symbols:
                print(f"  {GREEN}[+] Added Symbols:{RESET} {', '.join(delta.added_symbols)}")
            if delta.removed_symbols:
                print(f"  {RED}[-] Removed Symbols:{RESET} {', '.join(delta.removed_symbols)}")

            for sym_id, sym_delta in delta.symbol_deltas.items():
                if sym_delta.concurrency_diff:
                    old_c, new_c = sym_delta.concurrency_diff
                    print(f"  {RED}[!] Concurrency Synchronization Shift in {sym_id}:{RESET}")
                    print(f"      {old_c} -> {new_c}")
                if sym_delta.purity_diff:
                    old_p, new_p = sym_delta.purity_diff
                    color = RED if "pure" in old_p and "impure" in new_p else YELLOW
                    print(f"  {color}[*] Purity Shift in {sym_id}:{RESET} {old_p} -> {new_p}")
                if sym_delta.contract_diff:
                    old_ct, new_ct = sym_delta.contract_diff
                    print(f"  {YELLOW}[*] Contract Signature Shift in {sym_id}:{RESET} {old_ct} -> {new_ct}")
                for pre_diff in sym_delta.precondition_diffs:
                    if pre_diff.implication_holds:
                        print(f"  {GREEN}[✓] Invariant Proved (SMT):{RESET} {pre_diff.old_expr} => {pre_diff.new_expr}")
                    else:
                        print(f"  {RED}[x] Invariant Falsified (SMT Counterexample):{RESET} {pre_diff.old_expr} =/> {pre_diff.new_expr}")
                        if pre_diff.counterexample:
                            print(f"      Counterexample: {pre_diff.counterexample}")

    # Display Risks
    if report.risks:
        print(f"\n{CYAN}--- Identified Architectural Risks ---{RESET}")
        for r in report.risks:
            pfx = f"{RED}[ONE-WAY]{RESET}" if r.door_type == DoorType.ONE_WAY else f"{GREEN}[TWO-WAY]{RESET}"
            print(f"  {pfx} {BOLD}{r.category.value}{RESET}: {r.description}")
            print(f"      Blast Radius: {r.blast_radius}")

    # ADR Draft output if One-Way Door
    if report.adr_draft and report.door_type == DoorType.ONE_WAY:
        print(f"\n{MAGENTA}{BOLD}>>> Suggested Architecture Decision Record (ADR) Draft <<<{RESET}")
        print(report.adr_draft[:600] + ("\n... [truncated]" if len(report.adr_draft) > 600 else ""))

    return 1 if report.door_type == DoorType.ONE_WAY and args.strict else 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Execute Epistemic Zero-Trust Gate check against test suite baselines."""
    print(format_header("SOFTWARE FACTORY :: EPISTEMIC ZERO-TRUST GATE"))

    repo_dir = Path(args.repo) if args.repo else Path.cwd()
    guard = BaselineHashGuard()

    manifest_file = Path(args.manifest) if args.manifest else repo_dir / ".factory_baseline.json"

    # If --record is specified, store current state as trusted baseline
    if getattr(args, "record", False):
        manifest = guard.compute_manifest(repo_dir)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"{GREEN}[✓] Recorded baseline hash manifest for {len(manifest)} test files to {manifest_file}{RESET}")
        return 0

    if not manifest_file.exists():
        print(f"{YELLOW}[!] No baseline manifest found at {manifest_file}.{RESET}")
        print(f"    Run `factory verify --repo {repo_dir} --record` to establish initial cryptographic baseline.")
        return 0

    baseline_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    gate = ZeroTrustGate()
    report = gate.audit_patch(root_dir=repo_dir, baseline_manifest=baseline_manifest)

    print(report.summary())
    return 0 if report.passed else 1


def cmd_run(args: argparse.Namespace) -> int:
    """Execute specification intake, door classification, and synthesis orchestrator."""
    print(format_header("SOFTWARE FACTORY :: SPECIFICATION ORCHESTRATOR"))

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"{RED}Error: Spec file '{spec_path}' does not exist.{RESET}")
        return 1

    spec_text = spec_path.read_text(encoding="utf-8")
    print(f"{BOLD}Ingesting Specification:{RESET} {spec_path.name} ({len(spec_text.splitlines())} lines)")

    # Heuristic Door Detection on Specification
    is_one_way = False
    reasons = []

    if any(k in spec_text.lower() for k in ["drop table", "alter table", "migration", "database schema"]):
        is_one_way = True
        reasons.append("Modifies relational schema or database storage structures.")
    if any(k in spec_text.lower() for k in ["embedding model", "vector dimension", "pgvector", "hnsw"]):
        is_one_way = True
        reasons.append("Modifies vector dimensionality, distance metric, or vector store index.")
    if any(k in spec_text.lower() for k in ["concurrency", "mutex", "lock", "thread-safe", "race condition"]):
        is_one_way = True
        reasons.append("Modifies concurrency synchronization model or shared-state boundaries.")
    if any(k in spec_text.lower() for k in ["authentication", "oauth", "jwt", "session token", "rbac"]):
        is_one_way = True
        reasons.append("Modifies authentication mechanisms, cryptographic keys, or session lifespan.")

    print(f"\n{BOLD}Architectural Triage:{RESET} ", end="")
    if is_one_way:
        print(f"{RED}{BOLD}ONE-WAY DOOR DETECTED{RESET}")
        for r in reasons:
            print(f"  {RED}[!] Trigger:{RESET} {r}")
        print(f"\n{YELLOW}Mandating Socratic Architectural Debate before synthesis.{RESET}")
        engine = GovernanceEngine()
        adr_draft = engine.generate_adr_draft(
            risks=[],
            title=f"Selection of Architecture for {spec_path.stem}",
            context="\n".join(reasons),
        )
        print(f"\n{CYAN}Generated ADR Scaffold:{RESET}\n{adr_draft[:500]}...\n")
    else:
        print(f"{GREEN}{BOLD}TWO-WAY DOOR DETECTED{RESET}")
        print(f"  {GREEN}[✓] Localized scope; proceeding with autonomous test-driven synthesis.{RESET}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sf",
        description="Software Factory (sf): Autonomous Engineering Substrate with Intrinsic Semantic Parity.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available factory commands")

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit semantic delta (ΔS) and classify architectural doors")
    p_audit.add_argument("--pre", help="Path to pre-change source file")
    p_audit.add_argument("--post", help="Path to post-change source file")
    p_audit.add_argument("--strict", action="store_true", help="Exit with non-zero code on One-Way Doors")

    # verify
    p_verify = subparsers.add_parser("verify", help="Run Epistemic Zero-Trust Gate against baseline test manifest")
    p_verify.add_argument("--repo", default=".", help="Repository root directory")
    p_verify.add_argument("--manifest", help="Path to custom baseline manifest JSON")
    p_verify.add_argument("--record", action="store_true", help="Record current test suite as trusted baseline")

    # run
    p_run = subparsers.add_parser("run", help="Ingest specification and execute autonomous engineering cycle")
    p_run.add_argument("--spec", required=True, help="Path to specification markdown file")
    p_run.add_argument("--repo", default=".", help="Target repository directory")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        return cmd_audit(args)
    elif args.command == "verify":
        return cmd_verify(args)
    elif args.command == "run":
        return cmd_run(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
