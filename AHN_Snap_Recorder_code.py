from __future__ import annotations

import sys
import time
import datetime as dt
from pathlib import Path
from typing import Optional, Tuple

import cv2
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit,
    QHBoxLayout, QVBoxLayout, QMessageBox
)

# -----------------------------
# 설정/상수
# -----------------------------
DEFAULT_SOURCE = "0"  # 웹캠: "0", RTSP
SAVE_DIR = Path("videos");    SAVE_DIR.mkdir(exist_ok=True)
SNAP_DIR = Path("snapshots"); SNAP_DIR.mkdir(exist_ok=True)

# Windows 중심 실전 우선순위
CODEC_CANDIDATES: list[Tuple[str, str]] = [
    ("MJPG", ".avi"),   # Motion-JPEG: Windows에서 가장 안정적
    ("XVID", ".avi"),   # Xvid
    ("mp4v", ".mp4"),   # MPEG-4: 일부 환경에서 실패 가능
]

def timestamp_name(prefix: str, ext: str) -> str:
    """타임스탬프 기반 파일명 생성"""
    return f"{prefix}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"


class VideoRecorderUI(QWidget):
    """버튼 UI + 단축키 + 코덱 자동탐색 """

    # ---- 초기화/상태 ---------------------------------------------------------
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AHN_Snap-Recorder")

        # OpenCV 핸들/상태
        self.cap: Optional[cv2.VideoCapture] = None
        self.out: Optional[cv2.VideoWriter] = None
        self.is_recording: bool = False
        self.rec_start: float = 0.0

        # 표시/계산
        self.fps_ema: float = 0.0
        self.last_t: float = time.time()
        self.frame_size: Tuple[int, int] = (0, 0)   # (w, h)
        self.fps_cap: float = 20.0
        self.last_frame = None  # 스냅샷 버퍼

        # 코덱 자동 선택 결과
        self.working_codec: Optional[Tuple[str, str]] = None  # (codec, ext)
        self.out_path: Optional[Path] = None  # 녹화 출력 경로(또는 프레임 디렉터리)
        self.frame_count: int = 0            # 프레임 폴백 모드에서 사용

        self._build_ui()
        self._bind_shortcuts()
        self._find_working_codec()  # 코덱 호환성 탐색
        self.on_connect()           # 자동 연결(기본: 웹캠 0)

    # ---- UI 구성 ------------------------------------------------------------
    def _build_ui(self) -> None:
        self.video_label = QLabel("No video")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background:#111; color:#bbb;")

        self.source_edit = QLineEdit(DEFAULT_SOURCE)
        self.source_edit.setPlaceholderText("0 또는 rtsp://id:pw@ip/stream")
        self.source_edit.returnPressed.connect(self.on_connect)  # Enter → Connect

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect)

        self.record_btn = QPushButton("● REC")
        self.record_btn.setCheckable(True)
        self.record_btn.setStyleSheet(
            "QPushButton {background:#222; color:#e44; font-weight:bold; padding:8px 14px;}"
            "QPushButton:checked {background:#e44; color:white;}"
        )
        self.record_btn.clicked.connect(self.on_toggle_record)

        self.snapshot_btn = QPushButton("📸 Snapshot")
        self.snapshot_btn.clicked.connect(self.on_snapshot)

        self.quit_btn = QPushButton("Exit")
        self.quit_btn.clicked.connect(self.close)

        top = QHBoxLayout()
        top.addWidget(QLabel("Source:"))
        top.addWidget(self.source_edit, 1)
        top.addWidget(self.connect_btn)

        btns = QHBoxLayout()
        btns.addWidget(self.record_btn)
        btns.addWidget(self.snapshot_btn)
        btns.addStretch(1)
        btns.addWidget(self.quit_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.video_label, 1)
        layout.addLayout(btns)
        self.resize(960, 600)

        # 타이머: 프레임 풀링
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.grab_frame)

    def _bind_shortcuts(self) -> None:
        """키 입력 포커스 설정."""
        self.setFocusPolicy(Qt.StrongFocus)
        self.video_label.setFocusPolicy(Qt.ClickFocus)

    # ---- 코덱 자동 탐색 -----------------------------------------------------
    def _find_working_codec(self) -> None:
        """시스템에서 동작하는 코덱/확장자 조합을 하나 선택."""
        print("=== 코덱 호환성 테스트 시작 ===")
        test_size, test_fps = (640, 480), 20.0

        for codec, ext in CODEC_CANDIDATES:
            tmp_path = SAVE_DIR / f"codec_test_{codec}{ext}"
            writer = cv2.VideoWriter(str(tmp_path),
                                     cv2.VideoWriter_fourcc(*codec),
                                     test_fps, test_size)
            if writer.isOpened():
                writer.release()
                try: tmp_path.unlink()
                except: pass
                self.working_codec = (codec, ext)
                print(f"✓ {codec} ({ext}) - 사용 가능")
                break
            else:
                writer.release()
                print(f"✗ {codec} ({ext}) - 사용 불가")

        if self.working_codec:
            print(f"✓ 최종 선택: {self.working_codec[0]} 코덱")
        else:
            print("❌ 사용 가능한 코덱을 찾지 못했습니다. (프레임 저장 모드로 폴백)")

    # ---- 이벤트/단축키 ------------------------------------------------------
    def keyPressEvent(self, e: QKeyEvent) -> None:
        """Space: REC 토글 / S: 스냅샷 / ESC: 종료"""
        k = e.key()
        if   k == Qt.Key_Space:   self.on_toggle_record()
        elif k == Qt.Key_S:       self.on_snapshot()
        elif k == Qt.Key_Escape:  self.close()
        else:                     super().keyPressEvent(e)

    # ---- 연결/해제 ----------------------------------------------------------
    @staticmethod
    def _parse_source(text: str) -> int | str:
        """입력 문자열을 장치 인덱스(int) 또는 URL(str)로 변환."""
        t = text.strip()
        if t == "" or t == "0":
            return 0
        return int(t) if t.isdigit() else t

    def on_connect(self) -> None:
        """소스 연결: 첫 프레임으로 크기/FPS 확정 및 타이머 시작."""
        self._close_capture()
        src = self._parse_source(self.source_edit.text())
        self.cap = cv2.VideoCapture(src)

        if not self.cap.isOpened():
            self._error("영상 소스를 열 수 없습니다.\n(웹캠: 0 / RTSP: rtsp://id:pw@ip/stream)")
            self.video_label.setText("Failed to open source")
            return

        ok, frame = self.cap.read()
        if not ok:
            self._error("첫 프레임을 읽지 못했습니다.")
            self._close_capture()
            self.video_label.setText("Failed to read first frame")
            return

        h, w = frame.shape[:2]
        self.frame_size = (int(w), int(h))

        fps = self.cap.get(cv2.CAP_PROP_FPS)
        # 장치가 0/이상치 반환 시 안전값으로 보정 (1~30 클램프)
        self.fps_cap = float(fps) if fps and fps > 1 else 20.0
        self.fps_cap = max(1.0, min(self.fps_cap, 30.0))

        self.last_t = time.time()
        self.fps_ema = 0.0
        self.timer.start(10)
        self.video_label.setText("")
        print(f"연결 완료: {w}x{h}, FPS: {self.fps_cap}")

    def _close_capture(self) -> None:
        """캡처/레코더 리소스 해제."""
        if self.is_recording:
            self._stop_recording()
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    # ---- 녹화 로직 ----------------------------------------------------------
    def _open_writer(self, w: int, h: int) -> Tuple[Optional[cv2.VideoWriter], Path]:
        """
        동작 가능한 코덱이 있으면 VideoWriter를 열고,
        없으면 프레임 저장 디렉터리를 만들어 폴백한다.
        """
        if not self.working_codec:
            frames_dir = SAVE_DIR / f"frames_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            frames_dir.mkdir(exist_ok=True)
            return None, frames_dir

        codec, ext = self.working_codec
        out_path = SAVE_DIR / timestamp_name("rec", ext)
        writer = cv2.VideoWriter(
            str(out_path),
            cv2.VideoWriter_fourcc(*codec),
            float(self.fps_cap),
            (int(w), int(h))
        )
        if writer.isOpened():
            print(f"VideoWriter 생성 성공: {codec} 코덱, {self.fps_cap} FPS")
            return writer, out_path

        # 실패 시 프레임 저장 모드로 폴백
        try: writer.release()
        except: pass
        frames_dir = SAVE_DIR / f"frames_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        frames_dir.mkdir(exist_ok=True)
        print("VideoWriter 생성 실패 → 프레임 저장 모드로 전환")
        return None, frames_dir

    def _start_recording(self) -> None:
        """녹화 시작(파일 또는 프레임 폴백)."""
        if self.cap is None:
            return
        w, h = self.frame_size
        if w <= 0 or h <= 0:
            self._error("유효하지 않은 프레임 크기입니다.")
            return

        self.out, self.out_path = self._open_writer(w, h)
        self.frame_count = 0
        self.is_recording = True
        self.rec_start = time.time()
        self.record_btn.setText("■ STOP")

        if self.out is None:
            print(f"[REC] 프레임 저장 모드 시작 -> {self.out_path}")
        else:
            print(f"[REC] 비디오 녹화 시작 -> {self.out_path} ({w}x{h}, fps={self.fps_cap})")

    def _stop_recording(self) -> None:
        """녹화 종료 및 리소스 정리."""
        self.is_recording = False

        if self.out is not None:
            self.out.release()
            self.out = None
            print("[REC] 비디오 녹화 중지")
        else:
            # 프레임 폴백 모드였을 때 ffmpeg로 합치는 예시 안내
            print(f"[REC] 프레임 저장 완료: {self.frame_count}개")
            print(f"비디오 생성 예시: ffmpeg -r {self.fps_cap} -i {self.out_path}/frame_%06d.jpg "
                  f"-c:v libx264 -pix_fmt yuv420p output.mp4")

        self.record_btn.setChecked(False)
        self.record_btn.setText("● REC")

    def on_toggle_record(self) -> None:
        """버튼/Space로 REC 토글."""
        self._stop_recording() if self.is_recording else self._start_recording()

    # ---- 스냅샷 -------------------------------------------------------------
    def on_snapshot(self) -> None:
        """현재 프레임 PNG로 저장."""
        if self.last_frame is None:
            return
        path = SNAP_DIR / timestamp_name("snap", ".png")
        cv2.imwrite(str(path), self.last_frame)
        print(f"[SNAP] {path}")

    # ---- 프레임 루프/오버레이 -----------------------------------------------
    def _draw_overlays(self, frame_bgr):
        """FPS/REC 상태 오버레이 그리기."""
        now = time.time()
        dt_ = now - self.last_t
        self.last_t = now
        inst = (1.0 / dt_) if dt_ > 0 else 0.0
        self.fps_ema = 0.9 * self.fps_ema + 0.1 * inst

        h, w = frame_bgr.shape[:2]
        cv2.putText(frame_bgr, f"{w}x{h}  {self.fps_ema:05.2f} FPS",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)

        if self.is_recording:
            elapsed = int(now - self.rec_start)
            hh, mm, ss = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            if int(now) % 2 == 0:
                cv2.circle(frame_bgr, (25, 35), 10, (0, 0, 255), -1)

            mode = "VIDEO" if self.out is not None else "FRAMES"
            cv2.putText(frame_bgr, f"REC({mode}) {hh:02d}:{mm:02d}:{ss:02d}",
                        (45, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                        (0, 0, 255), 2, cv2.LINE_AA)
        return frame_bgr

    def grab_frame(self) -> None:
        """타이머 콜백: 프레임 읽기/표시/저장."""
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            self.timer.stop()
            self.video_label.setText("Stream ended / cannot read frame")
            return

        # 기록용(원본)과 표시용(오버레이) 분리
        frame_to_write = frame.copy()
        frame_disp = self._draw_overlays(frame)

        # 화면 표시 (BGR → RGB)
        rgb = cv2.cvtColor(frame_disp, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qimg))
        self.last_frame = frame_to_write

        # 녹화 중이면 파일 또는 프레임 폴더에 기록
        if self.is_recording:
            if self.out is not None:
                self.out.write(frame_to_write)
            else:
                assert self.out_path is not None
                frame_path = self.out_path / f"frame_{self.frame_count:06d}.jpg"
                cv2.imwrite(str(frame_path), frame_to_write)
                self.frame_count += 1

    # ---- 종료/에러 -----------------------------------------------------------
    def closeEvent(self, e) -> None:
        self.timer.stop()
        if self.is_recording:
            self._stop_recording()
        if self.cap is not None:
            self.cap.release()
        cv2.destroyAllWindows()
        e.accept()

    @staticmethod
    def _error(msg: str) -> None:
        QMessageBox.critical(None, "Error", msg)


def main() -> None:
    app = QApplication(sys.argv)
    ui = VideoRecorderUI()
    ui.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

