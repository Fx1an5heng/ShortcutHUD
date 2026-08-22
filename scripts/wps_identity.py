"""WPS semantic identity classification on one dedicated COM worker thread."""

from __future__ import annotations

import comtypes
from dataclasses import dataclass
import threading
import time
from typing import Callable, Protocol


WPS_WRITER = "WPS_WRITER"
WPS_PDF = "WPS_PDF"
WPS_PRESENTATION = "WPS_PRESENTATION"
WPS_UNKNOWN = "WPS_UNKNOWN"

HIGH_CONFIDENCE = "HIGH"
UNKNOWN_CONFIDENCE = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class WpsClassification:
    logical_app_id: str
    confidence: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WpsIdentityRequest:
    hwnd: int
    generation: int
    requested_at: float


@dataclass(frozen=True, slots=True)
class WpsIdentityResult:
    hwnd: int
    generation: int
    logical_app_id: str
    confidence: str
    evidence: tuple[str, ...]
    requested_at: float
    resolved_at: float
    duration_ms: float


class _Classifier(Protocol):
    def classify(self, hwnd: int) -> WpsClassification: ...

    def close(self) -> None: ...


def classify_wps_semantic_ancestry(
    classes: list[str] | tuple[str, ...],
    reached_foreground_root: bool,
) -> WpsClassification:
    """Classify only an unambiguous strong family bound to the foreground root."""

    if not reached_foreground_root:
        return WpsClassification(
            WPS_UNKNOWN,
            UNKNOWN_CONFIDENCE,
            ("focus_outside_foreground_root",),
        )

    class_set = {value for value in classes if isinstance(value, str) and value}
    matches: list[tuple[str, tuple[str, ...]]] = []

    writer_evidence = ["KxWpsView"]
    if "KxWpsView" in class_set:
        if "KxWpsDocPane" in class_set:
            writer_evidence.append("KxWpsDocPane")
        elif "KxWpsMainWindow" in class_set:
            writer_evidence.append("KxWpsMainWindow")
        else:
            writer_evidence = []
    else:
        writer_evidence = []
    if writer_evidence:
        matches.append((WPS_WRITER, tuple(writer_evidence)))

    pdf_required = ("KxPdfView", "KxPdfDocPane", "KxPdfMainWindow")
    if all(value in class_set for value in pdf_required):
        matches.append((WPS_PDF, pdf_required))

    presentation_evidence = ["KxWppView"]
    if "KxWppView" in class_set:
        if "KxWppSlidePane" in class_set:
            presentation_evidence.append("KxWppSlidePane")
        elif "KxWppMainWindow" in class_set:
            presentation_evidence.append("KxWppMainWindow")
        else:
            presentation_evidence = []
    else:
        presentation_evidence = []
    if presentation_evidence:
        matches.append((WPS_PRESENTATION, tuple(presentation_evidence)))

    if len(matches) == 1:
        logical_app_id, evidence = matches[0]
        return WpsClassification(logical_app_id, HIGH_CONFIDENCE, evidence)
    if len(matches) > 1:
        return WpsClassification(
            WPS_UNKNOWN,
            UNKNOWN_CONFIDENCE,
            tuple(f"conflicting_family:{logical_id}" for logical_id, _ in matches),
        )
    return WpsClassification(
        WPS_UNKNOWN,
        UNKNOWN_CONFIDENCE,
        ("no_strong_semantic_family",),
    )


class ComtypesWpsClassifier:
    """Read only the focused ControlView ancestry using UIAutomationCore."""

    MAX_ANCESTRY_DEPTH = 40

    def __init__(self) -> None:
        import comtypes.client

        uia = comtypes.client.GetModule("UIAutomationCore.dll")
        self._automation = comtypes.client.CreateObject(
            uia.CUIAutomation,
            interface=uia.IUIAutomation,
        )

    def classify(self, hwnd: int) -> WpsClassification:
        if not isinstance(hwnd, int) or hwnd <= 0:
            raise ValueError("A positive foreground HWND is required")

        automation = self._automation
        root = automation.ElementFromHandle(hwnd)
        focused = automation.GetFocusedElement()
        walker = automation.ControlViewWalker

        classes: list[str] = []
        reached_root = False
        current = focused
        for _ in range(self.MAX_ANCESTRY_DEPTH):
            if not current:
                break
            classes.append(str(current.CurrentClassName or ""))
            if automation.CompareElements(current, root):
                reached_root = True
                break
            current = walker.GetParentElement(current)

        return classify_wps_semantic_ancestry(classes, reached_root)

    def close(self) -> None:
        self._automation = None


class WpsIdentityWorker:
    """Coalesce identity requests and execute them in one COM MTA apartment."""

    def __init__(
        self,
        result_callback: Callable[[WpsIdentityResult], None],
        classifier_factory: Callable[[], _Classifier] = ComtypesWpsClassifier,
        thread_name: str = "ShortcutHUD-WpsIdentity",
    ) -> None:
        self._result_callback = result_callback
        self._classifier_factory = classifier_factory
        self._condition = threading.Condition()
        self._pending_request: WpsIdentityRequest | None = None
        self._latest_generation = -1
        self._accepting_requests = False
        self._stop_requested = False
        self._thread = threading.Thread(
            target=self._run,
            name=thread_name,
            daemon=True,
        )

    def start(self) -> None:
        with self._condition:
            if self._thread.is_alive() or self._accepting_requests:
                return
            self._accepting_requests = True
            self._thread.start()

    def submit(self, request: WpsIdentityRequest) -> bool:
        with self._condition:
            if not self._accepting_requests or self._stop_requested:
                return False
            self._latest_generation = max(
                self._latest_generation,
                request.generation,
            )
            self._pending_request = request
            self._condition.notify()
            return True

    def invalidate(self, generation: int) -> None:
        with self._condition:
            self._latest_generation = max(self._latest_generation, generation)
            self._pending_request = None
            self._condition.notify()

    def stop_accepting_requests(self) -> None:
        with self._condition:
            self._accepting_requests = False
            self._pending_request = None
            self._condition.notify()

    def stop(self, timeout: float = 1.0) -> bool:
        self.stop_accepting_requests()
        with self._condition:
            self._stop_requested = True
            self._condition.notify()
        if self._thread.is_alive():
            self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        classifier: _Classifier | None = None
        initialization_error: BaseException | None = None
        com_initialized = False
        try:
            try:
                # comtypes is imported by the owning/main thread so its process
                # atexit cleanup is paired there. UIA itself is created and used
                # only after this worker initializes its own MTA apartment.
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
                com_initialized = True
                classifier = self._classifier_factory()
            except BaseException as error:
                initialization_error = error

            while True:
                with self._condition:
                    while (
                        self._pending_request is None
                        and not self._stop_requested
                    ):
                        self._condition.wait()
                    if self._stop_requested:
                        return
                    request = self._pending_request
                    self._pending_request = None

                if request is None:
                    continue
                result = self._resolve_request(
                    request,
                    classifier,
                    initialization_error,
                )

                with self._condition:
                    is_current = (
                        not self._stop_requested
                        and request.generation == self._latest_generation
                    )
                if not is_current:
                    continue
                try:
                    self._result_callback(result)
                except BaseException:
                    # A consumer failure must not kill the COM worker.
                    continue
        finally:
            if classifier is not None:
                try:
                    classifier.close()
                except BaseException:
                    pass
            classifier = None
            if com_initialized:
                comtypes.CoUninitialize()

    @staticmethod
    def _resolve_request(
        request: WpsIdentityRequest,
        classifier: _Classifier | None,
        initialization_error: BaseException | None,
    ) -> WpsIdentityResult:
        started = time.perf_counter()
        try:
            if classifier is None:
                detail = (
                    type(initialization_error).__name__
                    if initialization_error is not None
                    else "unknown"
                )
                classification = WpsClassification(
                    WPS_UNKNOWN,
                    UNKNOWN_CONFIDENCE,
                    (f"worker_initialization_failed:{detail}",),
                )
            else:
                classification = classifier.classify(request.hwnd)
        except BaseException as error:
            classification = WpsClassification(
                WPS_UNKNOWN,
                UNKNOWN_CONFIDENCE,
                (f"classifier_failed:{type(error).__name__}",),
            )
        resolved_at = time.monotonic()
        return WpsIdentityResult(
            hwnd=request.hwnd,
            generation=request.generation,
            logical_app_id=classification.logical_app_id,
            confidence=classification.confidence,
            evidence=classification.evidence,
            requested_at=request.requested_at,
            resolved_at=resolved_at,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
