import cv2
import threading
import tkinter as tk
from tkinter import Label, Button
from PIL import Image, ImageTk
import time
import random
import platform
import subprocess
from collections import deque

from deepface import DeepFace

try:
    import pyttsx3
except:
    pyttsx3 = None

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

EMOTION_PHRASES = {
    "happy": ["I am feeling happy."],
    "sad": ["I am feeling sad."],
    "angry": ["I am upset."],
    "fear": ["I feel scared."],
    "surprise": ["That surprised me."],
    "disgust": ["I don't like this."],
    "neutral": ["I am okay."]
}

EMOJI_MAP = {
    "happy": "😊", "sad": "😢", "angry": "😠",
    "surprise": "😲", "fear": "😨",
    "disgust": "🤢", "neutral": "😐"
}

STRONG = ["angry", "sad", "fear", "disgust", "surprise"]

# ---------------- TTS ----------------
class TTSManager:
    def __init__(self):
        self.queue = []
        self.lock = threading.Condition()
        self.running = True
        self.is_speaking = False
        threading.Thread(target=self._loop, daemon=True).start()
        self.platform = platform.system().lower()

    def speak(self, text):
        with self.lock:
            self.queue.clear()
            self.queue.append(text)
            self.lock.notify()

    def stop(self):
        with self.lock:
            self.running = False
            self.lock.notify()

    def _loop(self):
        engine = None
        while True:
            with self.lock:
                while not self.queue and self.running:
                    self.lock.wait()
                if not self.running:
                    break
                text = self.queue.pop(0)

            self.is_speaking = True

            if self.platform.startswith("win"):
                text = text.replace("'", "''")
                subprocess.run([
                    "powershell",
                    "-Command",
                    f"Add-Type -AssemblyName System.speech;"
                    f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif pyttsx3:
                if engine is None:
                    engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()

            self.is_speaking = False


# ---------------- APP ----------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Emotion Fix Final")

        self.cap = None
        self.running = False

        self.last_emotion = None

        self.window = deque(maxlen=6)

        self.scan_line_pos = 0
        self.scan_direction = 1

        self.tts = TTSManager()

        self.build_ui()

    def build_ui(self):
        self.video = Label(self.root, bg="black")
        self.video.pack()

        self.label = Label(self.root, text="---", font=("Arial", 20))
        self.label.pack()

        self.phrase_label = Label(self.root, text="---", font=("Arial", 14),
                                 fg="white", bg="black")
        self.phrase_label.pack()

        Button(self.root, text="Start Camera", command=self.start).pack()
        Button(self.root, text="Stop Camera", command=self.stop).pack()

    def start(self):
        self.cap = cv2.VideoCapture(0)
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()

    # 🔥 HARD DECISION LOGIC
    def choose_emotion(self, scores):

        # 🔥 STEP 1: Strong emotion override
        for emo in STRONG:
            if scores.get(emo, 0) > 15:   # threshold
                return emo

        # 🔥 STEP 2: secondary check
        for emo in STRONG:
            if scores.get(emo, 0) > 8:
                return emo

        # 🔥 STEP 3: fallback normal max
        return max(scores, key=scores.get)

    def loop(self):
        frame_count = 0

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame_count += 1

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.2, 5)

            if len(faces) > 0:
                x, y, w, h = faces[0]

                cv2.rectangle(frame, (x, y), (x+w, y+h), (0,255,0), 3)

                # scanner
                line_y = y + self.scan_line_pos
                cv2.line(frame, (x, line_y), (x+w, line_y), (0,255,255), 2)

                self.scan_line_pos += 5 * self.scan_direction
                if self.scan_line_pos >= h or self.scan_line_pos <= 0:
                    self.scan_direction *= -1

                if frame_count % 5 == 0:
                    face_img = frame[y:y+h, x:x+w]

                    try:
                        result = DeepFace.analyze(
                            face_img,
                            actions=['emotion'],
                            enforce_detection=False
                        )

                        scores = result[0]['emotion']

                        emo = self.choose_emotion(scores)

                        self.window.append(emo)

                    except:
                        pass
            else:
                self.scan_line_pos = 0

            # voting
            if len(self.window) == self.window.maxlen:
                counts = {}
                for e in self.window:
                    counts[e] = counts.get(e,0)+1

                stable = max(counts, key=counts.get)

                if stable != self.last_emotion:
                    self.last_emotion = stable

                    text = random.choice(EMOTION_PHRASES[stable])
                    self.tts.speak(text)

                    emoji = EMOJI_MAP.get(stable,"")

                    self.root.after(0, lambda: self.label.config(
                        text=f"{stable.upper()} {emoji}"
                    ))

                    self.root.after(0, lambda t=text: self.phrase_label.config(text=t))

            # display
            if frame_count % 2 == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = ImageTk.PhotoImage(Image.fromarray(rgb))
                self.root.after(0, lambda img=img: self.video.config(image=img))

        if self.cap:
            self.cap.release()

    def on_close(self):
        self.stop()
        self.tts.stop()
        self.root.destroy()


# RUN
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()