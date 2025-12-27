# camera_manager.py

import cv2
import threading
import time
from queue import Queue

class CameraManager:
    def __init__(self):
        self.cap = None
        self.active = False

        self.current_frame = None
        self.detect_frame = None

        self.frame_lock = threading.Lock()
        self.detect_lock = threading.Lock()

        self.frame_queue = Queue(maxsize=1)
        self.capture_thread = None
        self.on_detection = None

        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()


    def set_detection_callback(self, cb):
        self.on_detection = cb


    def start(self, source):
        """Start RTSP / HTTP / USB camera"""
        self.stop()
        print(f"🎥 Starting camera stream: {source}")

        self.cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        if not self.cap.isOpened():
            print("❌ Cannot open camera")
            return False

        self.active = True
        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.capture_thread.start()

        return True


    def stop(self):
        print("🛑 Stopping camera ...")
        self.active = False
        time.sleep(0.1)

        if self.cap:
            self.cap.release()
            self.cap = None

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                break

        print("✅ Camera stopped")


    def _capture_worker(self):
        while self.active and self.cap:
            ret, frame = self.cap.read()

            if not ret or frame is None:
                time.sleep(0.02)
                continue

            # FPS counter
            self.frame_count += 1
            now = time.time()
            if now - self.last_fps_time >= 1:
                self.fps = self.frame_count / (now - self.last_fps_time)
                self.frame_count = 0
                self.last_fps_time = now

            with self.frame_lock:
                self.current_frame = frame.copy()

            with self.detect_lock:
                self.detect_frame = frame.copy()

            if self.frame_queue.full():
                try:
                    self.frame_queue.get_nowait()
                except:
                    pass

            self.frame_queue.put(frame, block=False)

        print("🔚 Capture Thread Ended")


    def get_stream_frame(self):
        with self.frame_lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None


    def get_detection_frame(self):
        with self.detect_lock:
            if self.detect_frame is not None:
                return self.detect_frame.copy()
            return None


    def generate_stream(self):
        """MJPEG feed generator"""
        while True:
            if not self.active:
                time.sleep(0.1)
                continue

            frame = self.get_stream_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )


camera_manager = CameraManager()
