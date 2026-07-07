import sys
import threading
import time
import random
import keyboard
import soundcard as sc
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
    update_text = pyqtSignal(str)

class InvisibleOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signaler = TranscriptionSignaler()
        self.signaler.update_text.connect(self.update_label)
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
        self.setGeometry(100, 100, 900, 150)

        self.central_widget = QWidget()
        self.layout = QVBoxLayout()

        self.text_label = QLabel("Connecting to AI Server...", self)
        self.text_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.text_label.setStyleSheet("""
            QLabel {
                color: #00FF00;
                background-color: rgba(0, 0, 0, 180);
                padding: 15px;
                border-radius: 8px;
            }
        """)
        self.text_label.setWordWrap(True)
        self.layout.addWidget(self.text_label)

        self.central_widget.setLayout(self.layout)
        self.setCentralWidget(self.central_widget)

    def apply_capture_evasion(self):
        if sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)

    def update_label(self, text):
        prefix = "[MOCK MODE] " if self.mock_mode else ""
        self.text_label.setText(f"{prefix}{text}")

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def toggle_mock_mode(self):
        self.mock_mode = not self.mock_mode
        if self.mock_mode:
            self.update_label("Mock interview mode activated.")
        else:
            self.update_label("Listening to call audio...")

    def setup_hotkeys(self):
        keyboard.add_hotkey('ctrl+shift+h', self.toggle_visibility)
        keyboard.add_hotkey('ctrl+shift+m', self.toggle_mock_mode)

def record_system_audio(duration=5, sample_rate=16000):
    """Intercepts audio playing through the default speakers (interviewer's voice)."""
    try:
        default_speaker = sc.default_speaker()
        # include_loopback=True is the magic flag that captures speaker output
        loopback_mic = sc.get_microphone(default_speaker.id, include_loopback=True)

        with loopback_mic.recorder(samplerate=sample_rate) as mic:
            data = mic.record(numframes=sample_rate * duration)

            # Convert audio data from float32 to int16 for the .wav file
            mono_data = data[:, 0] if len(data.shape) > 1 else data
            int16_data = np.int16(mono_data * 32767)
            return int16_data, sample_rate

    except Exception as e:
        print(f"System Audio Capture Error: {e}")
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

    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to the server."
    except Exception as e:
        return "Error communicating with server."

def ai_processing_thread(signaler, overlay):
    time.sleep(1)
    signaler.update_text.emit("System Audio active. Waiting for call to start...")

    while True:
        if overlay.mock_mode:
            time.sleep(4)
            simulated_responses = [
                "Suggested Answer: Discuss how you structured your React components and managed state.",
                "Suggested Answer: Mention your implementation of JWT authentication in the Spring Boot backend."
            ]
            signaler.update_text.emit(random.choice(simulated_responses))
        else:
            # Capture the interviewer's voice from the speakers
            audio_data, sample_rate = record_system_audio(duration=5)

            if audio_data is not None:
                # Calculate volume to ensure someone is actually speaking
                volume = np.linalg.norm(audio_data) / len(audio_data)
                if volume > 50.0:  # Threshold adjusted for int16 data
                    signaler.update_text.emit("Sending to server...")
                    ai_response = process_audio_via_server(audio_data, sample_rate)

                    if ai_response:
                        signaler.update_text.emit(ai_response)
                else:
                    signaler.update_text.emit("Listening to call audio...")

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