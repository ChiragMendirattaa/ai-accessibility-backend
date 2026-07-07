import sys
import threading
import time
import random
import keyboard
import sounddevice as sd
from scipy.io import wavfile
import numpy as np
import os
import tempfile
import requests

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont

# The address of your local FastAPI server
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
            self.update_label("Listening to microphone...")

    def setup_hotkeys(self):
        keyboard.add_hotkey('ctrl+shift+h', self.toggle_visibility)
        keyboard.add_hotkey('ctrl+shift+m', self.toggle_mock_mode)

def record_audio_chunk(duration=5, sample_rate=16000):
    try:
        recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='int16')
        sd.wait()
        return recording, sample_rate
    except Exception as e:
        print(f"Audio recording error: {e}")
        return None, sample_rate

def process_audio_via_server(audio_data, sample_rate):
    """Saves audio locally, POSTs it to the FastAPI server, and returns the answer."""
    try:
        # Save to temporary .wav file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            wavfile.write(temp_audio.name, sample_rate, audio_data)
            temp_filename = temp_audio.name

        # Send the file to your FastAPI server
        with open(temp_filename, "rb") as file:
            files = {"audio_file": (temp_filename, file, "audio/wav")}
            response = requests.post(SERVER_URL, files=files)

        os.remove(temp_filename) # Clean up the file

        if response.status_code == 200:
            return response.json().get("suggestion", "")
        else:
            print(f"Server returned status {response.status_code}: {response.text}")
            return "Error: Server failed to process audio."

    except requests.exceptions.ConnectionError:
        return "Error: Cannot connect to the server. Is it running?"
    except Exception as e:
        print(f"Client Error: {e}")
        return "Error communicating with server."

def ai_processing_thread(signaler, overlay):
    time.sleep(1)
    signaler.update_text.emit("Microphone active. Waiting for speech...")

    while True:
        if overlay.mock_mode:
            time.sleep(4)
            simulated_responses = [
                "Suggested Answer: Discuss how you structured your React components and managed state.",
                "Suggested Answer: Mention your implementation of JWT authentication in the Spring Boot backend."
            ]
            signaler.update_text.emit(random.choice(simulated_responses))
        else:
            audio_data, sample_rate = record_audio_chunk(duration=5)

            if audio_data is not None:
                # Calculate volume to skip processing if the room is quiet
                volume = np.linalg.norm(audio_data) / len(audio_data)
                if volume > 2.0:
                    signaler.update_text.emit("Sending to server...")
                    ai_response = process_audio_via_server(audio_data, sample_rate)

                    if ai_response:
                        signaler.update_text.emit(ai_response)
                else:
                    signaler.update_text.emit("Listening to microphone...")

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