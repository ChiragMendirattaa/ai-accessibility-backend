import sys
import threading
import time
import random
import keyboard
from scipy.io import wavfile
import numpy as np
import os
import tempfile
import requests

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont

# The public address of your Render server
SERVER_URL = "https://ai-accessibility-backend.onrender.com/api/process-audio"

class TranscriptionSignaler(QObject):
    # We now have two separate signals for the UI
    update_status = pyqtSignal(str)
    update_answer = pyqtSignal(str)

class InvisibleOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signaler = TranscriptionSignaler()
        self.signaler.update_status.connect(self.set_status)
        self.signaler.update_answer.connect(self.set_answer)
        self.mock_mode = False

        self.setup_ui()
        self.apply_capture_evasion()
        self.setup_hotkeys()

    def setup_ui(self):
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint |
                Qt.FramelessWindowHint |
                Qt.Tool |
                Qt.WindowTransparentForInput
            )
            self.setAttribute(Qt.WA_TranslucentBackground)

            # 1. INCREASE HEIGHT: Changed from 200 to 350 to fit longer answers
            self.setGeometry(100, 100, 900, 350)

            self.central_widget = QWidget()
            self.central_widget.setStyleSheet("background-color: rgba(0, 0, 0, 180); border-radius: 12px;")
            self.layout = QVBoxLayout()

            # 2. INCREASE PADDING: Gives the text more breathing room on the edges
            self.layout.setContentsMargins(25, 25, 25, 25)

            # 3. TOP ALIGNMENT: Prevents the text from stretching out of the middle
            self.layout.setAlignment(Qt.AlignTop)

            # The small status label
            self.status_label = QLabel("Connecting to AI Server...", self)
            status_font = QFont("Arial", 10)
            status_font.setItalic(True)
            self.status_label.setFont(status_font)
            self.status_label.setStyleSheet("color: #AAAAAA; background: transparent;")
            self.layout.addWidget(self.status_label)

            # The large answer label
            self.answer_label = QLabel("Waiting for first question...", self)
            self.answer_label.setFont(QFont("Arial", 16, QFont.Bold))
            self.answer_label.setStyleSheet("color: #00FF00; background: transparent;")
            self.answer_label.setWordWrap(True)

            # 4. TEXT ALIGNMENT: Forces the words to start at the top-left
            self.answer_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.layout.addWidget(self.answer_label)

            self.central_widget.setLayout(self.layout)
            self.setCentralWidget(self.central_widget)

    def apply_capture_evasion(self):
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)

    def set_status(self, text):
        prefix = "[MOCK MODE] " if self.mock_mode else ""
        self.status_label.setText(f"{prefix}{text}")

    def set_answer(self, text):
        self.answer_label.setText(text)

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def toggle_mock_mode(self):
        self.mock_mode = not self.mock_mode
        if self.mock_mode:
            self.set_status("Mock interview mode activated.")
            self.set_answer("Simulating responses...")
        else:
            self.set_status("Listening to call audio...")
            self.set_answer("Waiting for next question...")

    def quit_app(self):
        os._exit(0)

    def setup_hotkeys(self):
        keyboard.add_hotkey('ctrl+shift+h', self.toggle_visibility)
        keyboard.add_hotkey('ctrl+shift+m', self.toggle_mock_mode)
        keyboard.add_hotkey('ctrl+shift+q', self.quit_app)

def record_system_audio(duration=5, sample_rate=16000):
    import soundcard as sc
    try:
        default_speaker = sc.default_speaker()
        loopback_mic = sc.get_microphone(default_speaker.id, include_loopback=True)

        with loopback_mic.recorder(samplerate=sample_rate) as mic:
            data = mic.record(numframes=sample_rate * duration)
            mono_data = data[:, 0] if len(data.shape) > 1 else data
            int16_data = np.int16(mono_data * 32767)
            return int16_data, sample_rate
    except Exception as e:
        return None, sample_rate

def process_audio_via_server(audio_data, sample_rate):
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            wavfile.write(temp_audio.name, sample_rate, audio_data)
            temp_filename = temp_audio.name

        with open(temp_filename, "rb") as file:
            files = {"audio_file": (temp_filename, file, "audio/wav")}
            response = requests.post(SERVER_URL, files=files)

        os.remove(temp_filename)

        if response.status_code == 200:
            return response.json().get("suggestion", "")
        else:
            return "Error: Server failed to process audio."
    except Exception:
        return "Error communicating with server."

def ai_processing_thread(signaler, overlay):
    time.sleep(1)
    signaler.update_status.emit("System Audio active.")

    while True:
        if overlay.mock_mode:
            time.sleep(4)
            simulated_responses = [
                "I structured the React components by breaking them down into atomic design principles, ensuring reusability across the application.",
                "For authentication, I implemented a robust JWT flow in the Spring Boot backend, storing tokens securely in HttpOnly cookies."
            ]
            signaler.update_answer.emit(random.choice(simulated_responses))
        else:
            audio_data, sample_rate = record_system_audio(duration=5)

            if audio_data is not None:
                volume = np.linalg.norm(audio_data) / len(audio_data)

                if volume > 2.0:
                    signaler.update_status.emit("Processing audio... Sending to server.")
                    ai_response = process_audio_via_server(audio_data, sample_rate)

                    if ai_response:
                        signaler.update_answer.emit(ai_response)
                        signaler.update_status.emit("Response received. Listening...")
                else:
                    signaler.update_status.emit("Listening to call audio...")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InvisibleOverlay()
    window.show()

    backend_thread = threading.Thread(
        target=ai_processing_thread,
        args=(window.signaler, window),
        daemon=True
    )
    backend_thread.start()

    sys.exit(app.exec_())