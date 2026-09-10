"""
Epistemic Zero-Trust Verification Substrate for Software Factory.
Prevents reward-hacking, tautological test debt, and assertion weakening
through cryptographic baseline locking and AST-level assertion audits.
"""

from __future__ import annotations
import ast
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class BaselineVerificationResult:
    """Result of baseline cryptographic and AST assertion audit."""
    passed: bool
    deleted_files: List[str] = field(default_factory=list)
    weakened_files: List[str] = field(default_factory=list)
    skipped_tests: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    reward_hacking_detected: bool = False

    def summary(self) -> str:
        lines = []
        status = "PASSED" if self.passed else "FAILED (ZERO-TRUST REJECTION)"
        lines.append(f"Baseline Hash & Assertion Audit: {status}")
        if self.deleted_files:
            lines.append(f"  [!] Deleted Test Files: {', '.join(self.deleted_files)}")
        if self.weakened_files:
            lines.append(f"  [!] Weakened Assertion Files: {', '.join(self.weakened_files)}")
        if self.skipped_tests:
            lines.append(f"  [!] Injected Skipped Tests: {', '.join(self.skipped_tests)}")
        for v in self.violations:
            lines.append(f"  [x] {v}")
        return "\n".join(lines)


class AssertionVisitor(ast.NodeVisitor):
    """AST visitor extracting assertion signatures and skip decorators."""

    def __init__(self) -> None:
        self.assert_count: int = 0
        self.assert_expressions: List[str] = []
        self.skipped_functions: List[str] = []
        self.trivial_asserts: int = 0

    def visit_Assert(self, node: ast.Assert) -> None:
        self.assert_count += 1
        expr_str = ast.unparse(node.test)
        self.assert_expressions.append(expr_str)
        # Detect trivial assertions like `assert True` or `assert 1`
        if isinstance(node.test, ast.Constant) and bool(node.test.value) is True:
            self.trivial_asserts += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_decorators(node.name, node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_decorators(node.name, node.decorator_list)
        self.generic_visit(node)

    def _check_decorators(self, func_name: str, decorators: List[ast.expr]) -> None:
        for deco in decorators:
            deco_str = ast.unparse(deco)
            if any(skip_tag in deco_str for skip_tag in ["skip", "skipif", "xfail"]):
                self.skipped_functions.append(f"{func_name} ({deco_str})")


class BaselineHashGuard:
    """
    Guarantees that autonomous coding agents do not modify, bypass, or delete
    existing unit tests or invariant contracts in order to achieve green builds.
    """

    DEFAULT_PATTERNS = [
        "test_*.py",
        "*_test.py",
        "*_spec.py",
        "tests/**/*.py",
    ]

    @staticmethod
    def sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def compute_manifest(self, root_dir: Path, patterns: Optional[List[str]] = None) -> Dict[str, str]:
        """Compute SHA-256 hash map of all test files relative to root_dir."""
        patterns = patterns or self.DEFAULT_PATTERNS
        manifest: Dict[str, str] = {}

        matched_paths: Set[Path] = set()
        for pat in patterns:
            for p in root_dir.glob(pat):
                if p.is_file() and not any(part.startswith((".", "__pycache__", "venv", ".venv")) for part in p.parts):
                    matched_paths.add(p)

        for p in sorted(matched_paths):
            rel_path = str(p.relative_to(root_dir))
            manifest[rel_path] = self.sha256_file(p)

        return manifest

    def verify_files(
        self,
        baseline_manifest: Dict[str, str],
        root_dir: Path,
        original_contents: Optional[Dict[str, str]] = None,
    ) -> BaselineVerificationResult:
        """
        Verify that test files in root_dir have not been weakened or deleted
        relative to the baseline manifest.
        """
        deleted_files: List[str] = []
        weakened_files: List[str] = []
        skipped_tests: List[str] = []
        violations: List[str] = []
        reward_hacking = False

        for rel_path, baseline_hash in baseline_manifest.items():
            test_file = root_dir / rel_path
            if not test_file.exists():
                deleted_files.append(rel_path)
                violations.append(f"Security Alert: Pre-existing test file '{rel_path}' was deleted.")
                reward_hacking = True
                continue

            current_hash = self.sha256_file(test_file)
            if current_hash != baseline_hash:
                # File was modified - analyze AST for assertion weakening
                current_text = test_file.read_text(encoding="utf-8", errors="ignore")
                orig_text = (original_contents or {}).get(rel_path)

                try:
                    curr_ast = ast.parse(current_text)
                    curr_vis = AssertionVisitor()
                    curr_vis.visit(curr_ast)

                    if curr_vis.skipped_functions:
                        skipped_tests.extend([f"{rel_path}::{fn}" for fn in curr_vis.skipped_functions])
                        violations.append(
                            f"Reward Hacking: Test file '{rel_path}' injected skip decorator: "
                            f"{curr_vis.skipped_functions}"
                        )
                        reward_hacking = True

                    if curr_vis.trivial_asserts > 0:
                        violations.append(
                            f"Reward Hacking: Test file '{rel_path}' contains {curr_vis.trivial_asserts} "
                            f"trivial assertions (e.g. `assert True`)."
                        )
                        reward_hacking = True

                    if orig_text is not None:
                        orig_ast = ast.parse(orig_text)
                        orig_vis = AssertionVisitor()
                        orig_vis.visit(orig_ast)

                        if curr_vis.assert_count < orig_vis.assert_count:
                            dropped = orig_vis.assert_count - curr_vis.assert_count
                            weakened_files.append(rel_path)
                            violations.append(
                                f"Reward Hacking: Assertion count dropped by {dropped} in '{rel_path}' "
                                f"({orig_vis.assert_count} -> {curr_vis.assert_count})."
                            )
                            reward_hacking = True
                except SyntaxError:
                    violations.append(f"SyntaxError in modified test file '{rel_path}'.")

        passed = len(deleted_files) == 0 and len(weakened_files) == 0 and len(skipped_tests) == 0 and not reward_hacking

        return BaselineVerificationResult(
            passed=passed,
            deleted_files=deleted_files,
            weakened_files=weakened_files,
            skipped_tests=skipped_tests,
            violations=violations,
            reward_hacking_detected=reward_hacking,
        )


@dataclass
class ZeroTrustReport:
    """Consolidated report from the Epistemic Zero-Trust Gate."""
    passed: bool
    baseline_result: BaselineVerificationResult
    contract_violations: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["=" * 60, "EPISTEMIC ZERO-TRUST GATE EVALUATION", "=" * 60]
        lines.append(f"Overall Gate Status: {'PASSED' if self.passed else 'REJECTED'}")
        lines.append(self.baseline_result.summary())
        if self.contract_violations:
            lines.append("\n[!] Contract Violations:")
            for c in self.contract_violations:
                lines.append(f"  - {c}")
        return "\n".join(lines)


class ZeroTrustGate:
    """
    Enforces the Zero-Trust verification substrate.
    Validates cryptographic test baselines, catches tautological test deletions,
    and checks invariant contracts.
    """

    def __init__(self) -> None:
        self.guard = BaselineHashGuard()

    def audit_patch(
        self,
        root_dir: Path,
        baseline_manifest: Dict[str, str],
        original_contents: Optional[Dict[str, str]] = None,
        contract_violations: Optional[List[str]] = None,
    ) -> ZeroTrustReport:
        baseline_res = self.guard.verify_files(
            baseline_manifest=baseline_manifest,
            root_dir=root_dir,
            original_contents=original_contents,
        )
        violations = list(contract_violations or [])
        passed = baseline_res.passed and len(violations) == 0

        reasons: List[str] = []
        if not baseline_res.passed:
            reasons.append("Baseline test assertions were deleted, weakened, or skipped.")
        if violations:
            reasons.append(f"{len(violations)} formal contract violations detected.")

        return ZeroTrustReport(
            passed=passed,
            baseline_result=baseline_res,
            contract_violations=violations,
            reasons=reasons,
        )
