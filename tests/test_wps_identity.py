from __future__ import annotations

import threading
import time
import unittest

from scripts.wps_identity import (
    HIGH_CONFIDENCE,
    UNKNOWN_CONFIDENCE,
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
    WpsClassification,
    WpsIdentityRequest,
    WpsIdentityWorker,
    classify_wps_semantic_ancestry,
)


class _SequenceClassifier:
    def __init__(self, values: list[object]) -> None:
        self._values = iter(values)
        self.closed = False

    def classify(self, _hwnd: int) -> WpsClassification:
        value = next(self._values)
        if isinstance(value, BaseException):
            raise value
        assert isinstance(value, WpsClassification)
        return value

    def close(self) -> None:
        self.closed = True


class _BlockingClassifier:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = False

    def classify(self, hwnd: int) -> WpsClassification:
        self.started.set()
        self.release.wait(1.0)
        identity = WPS_WRITER if hwnd == 123 else WPS_PDF
        return WpsClassification(identity, HIGH_CONFIDENCE, (identity,))

    def close(self) -> None:
        self.closed = True


def _request(hwnd: int, generation: int) -> WpsIdentityRequest:
    return WpsIdentityRequest(hwnd, generation, time.monotonic())


class WpsSemanticClassificationTests(unittest.TestCase):
    def test_writer_semantic_ancestry(self) -> None:
        result = classify_wps_semantic_ancestry(
            ["KxWpsView", "KxWpsDocPane", "KxWpsMainWindow"],
            True,
        )
        self.assertEqual(result.logical_app_id, WPS_WRITER)
        self.assertEqual(result.confidence, HIGH_CONFIDENCE)

    def test_pdf_semantic_ancestry(self) -> None:
        result = classify_wps_semantic_ancestry(
            ["KxPdfView", "KxPdfDocPane", "KxPdfMainWindow"],
            True,
        )
        self.assertEqual(result.logical_app_id, WPS_PDF)
        self.assertEqual(result.confidence, HIGH_CONFIDENCE)

    def test_presentation_semantic_ancestry(self) -> None:
        result = classify_wps_semantic_ancestry(
            ["KxWppView", "KxWppSlidePane", "KxWppMainWindow"],
            True,
        )
        self.assertEqual(result.logical_app_id, WPS_PRESENTATION)
        self.assertEqual(result.confidence, HIGH_CONFIDENCE)

    def test_home_is_unknown(self) -> None:
        result = classify_wps_semantic_ancestry(
            ["QWidget", "KHyperionSpace::StartPage", "KPromeMainWindow"],
            True,
        )
        self.assertEqual(result.logical_app_id, WPS_UNKNOWN)
        self.assertEqual(result.confidence, UNKNOWN_CONFIDENCE)

    def test_conflicting_strong_families_are_unknown(self) -> None:
        result = classify_wps_semantic_ancestry(
            [
                "KxWpsView",
                "KxWpsDocPane",
                "KxPdfView",
                "KxPdfDocPane",
                "KxPdfMainWindow",
            ],
            True,
        )
        self.assertEqual(result.logical_app_id, WPS_UNKNOWN)

    def test_foreign_root_is_unknown(self) -> None:
        result = classify_wps_semantic_ancestry(
            ["KxPdfView", "KxPdfDocPane", "KxPdfMainWindow"],
            False,
        )
        self.assertEqual(result.logical_app_id, WPS_UNKNOWN)
        self.assertIn("focus_outside_foreground_root", result.evidence)


class WpsIdentityWorkerTests(unittest.TestCase):
    def test_latest_request_wins_and_stale_result_is_discarded(self) -> None:
        classifier = _BlockingClassifier()
        results = []
        delivered = threading.Event()
        worker = WpsIdentityWorker(
            lambda result: (results.append(result), delivered.set()),
            classifier_factory=lambda: classifier,
        )
        worker.start()
        try:
            worker.submit(_request(123, 10))
            self.assertTrue(classifier.started.wait(1.0))
            worker.submit(_request(456, 11))
            worker.submit(_request(456, 13))
            classifier.release.set()
            self.assertTrue(delivered.wait(1.0))
            self.assertEqual([result.generation for result in results], [13])
            self.assertEqual(results[0].logical_app_id, WPS_PDF)
        finally:
            classifier.release.set()
            self.assertTrue(worker.stop())

    def test_same_hwnd_can_change_subtype_without_cache(self) -> None:
        classifier = _SequenceClassifier(
            [
                WpsClassification(WPS_WRITER, HIGH_CONFIDENCE, ("writer",)),
                WpsClassification(WPS_PDF, HIGH_CONFIDENCE, ("pdf",)),
            ]
        )
        results = []
        delivered = threading.Event()

        def on_result(result: object) -> None:
            results.append(result)
            delivered.set()

        worker = WpsIdentityWorker(on_result, classifier_factory=lambda: classifier)
        worker.start()
        try:
            worker.submit(_request(123, 1))
            self.assertTrue(delivered.wait(1.0))
            delivered.clear()
            worker.submit(_request(123, 2))
            self.assertTrue(delivered.wait(1.0))
            self.assertEqual(
                [result.logical_app_id for result in results],
                [WPS_WRITER, WPS_PDF],
            )
        finally:
            self.assertTrue(worker.stop())

    def test_classifier_failure_publishes_unknown_and_worker_survives(self) -> None:
        classifier = _SequenceClassifier(
            [
                RuntimeError("RPC failure"),
                WpsClassification(WPS_WRITER, HIGH_CONFIDENCE, ("writer",)),
            ]
        )
        results = []
        delivered = threading.Event()

        def on_result(result: object) -> None:
            results.append(result)
            delivered.set()

        worker = WpsIdentityWorker(on_result, classifier_factory=lambda: classifier)
        worker.start()
        try:
            worker.submit(_request(123, 1))
            self.assertTrue(delivered.wait(1.0))
            self.assertEqual(results[0].logical_app_id, WPS_UNKNOWN)
            delivered.clear()
            worker.submit(_request(123, 2))
            self.assertTrue(delivered.wait(1.0))
            self.assertTrue(worker.is_alive)
            self.assertEqual(results[1].logical_app_id, WPS_WRITER)
        finally:
            self.assertTrue(worker.stop())

    def test_classifier_initialization_failure_is_unknown_and_worker_survives(self) -> None:
        results = []
        delivered = threading.Event()

        def fail_to_initialize() -> _SequenceClassifier:
            raise RuntimeError("COM initialization failure")

        worker = WpsIdentityWorker(
            lambda result: (results.append(result), delivered.set()),
            classifier_factory=fail_to_initialize,
        )
        worker.start()
        try:
            worker.submit(_request(123, 1))
            self.assertTrue(delivered.wait(1.0))
            self.assertTrue(worker.is_alive)
            self.assertEqual(results[0].logical_app_id, WPS_UNKNOWN)
            self.assertIn(
                "worker_initialization_failed:RuntimeError",
                results[0].evidence,
            )
        finally:
            self.assertTrue(worker.stop())

    def test_slow_classifier_does_not_block_submitter(self) -> None:
        classifier = _BlockingClassifier()
        delivered = threading.Event()
        worker = WpsIdentityWorker(
            lambda _result: delivered.set(),
            classifier_factory=lambda: classifier,
        )
        worker.start()
        try:
            started = time.perf_counter()
            self.assertTrue(worker.submit(_request(123, 1)))
            elapsed_ms = (time.perf_counter() - started) * 1000
            self.assertLess(elapsed_ms, 20)
            self.assertTrue(classifier.started.wait(1.0))
            classifier.release.set()
            self.assertTrue(delivered.wait(1.0))
        finally:
            classifier.release.set()
            self.assertTrue(worker.stop())

    def test_worker_shutdown_closes_classifier(self) -> None:
        classifier = _SequenceClassifier([])
        worker = WpsIdentityWorker(
            lambda _result: None,
            classifier_factory=lambda: classifier,
        )
        worker.start()
        self.assertTrue(worker.stop())
        self.assertFalse(worker.is_alive)
        self.assertTrue(classifier.closed)


if __name__ == "__main__":
    unittest.main()
