import threading
import unittest
from unittest.mock import patch

from security import face_guard


class FakeCapture:
    def __init__(self):
        self.read_calls = 0
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        self.read_calls += 1
        return True, object()

    def release(self):
        self.released = True


class FakeCV2:
    CAP_DSHOW = 700

    def __init__(self):
        self.capture = FakeCapture()

    def VideoCapture(self, *_args):
        return self.capture


class FakeFace:
    normed_embedding = [1.0, 0.0]


class FakeAnalysis:
    def __init__(self):
        self.calls = 0

    def get(self, _frame):
        self.calls += 1
        return [FakeFace()]


class ReconhecimentoFacialTests(unittest.TestCase):
    def test_para_e_libera_camera_apos_primeiro_reconhecimento(self):
        cv2 = FakeCV2()
        analise = FakeAnalysis()
        estados = []
        with patch.object(face_guard, "_engine", return_value=(cv2, analise)), \
             patch.object(face_guard, "_load", return_value={"Victor": [[1.0, 0.0]]}):
            face_guard.run(
                lambda _when: self.fail("Não deve alertar uma pessoa reconhecida"),
                on_status=lambda status, name, score: estados.append((status, name, score)),
                stop_event=threading.Event(),
            )
        self.assertEqual(analise.calls, 1)
        self.assertEqual(cv2.capture.read_calls, 1)
        self.assertTrue(cv2.capture.released)
        self.assertEqual(estados[-1][0], "recognized")
        self.assertEqual(estados[-1][1], "Victor")


if __name__ == "__main__":
    unittest.main()
