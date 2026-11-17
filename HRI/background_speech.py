import threading
import queue
import transcribe_audio as mic

class SpeechListenerThread(threading.Thread):
    def __init__(self, display_inst=None):
        super().__init__()
        self.daemon = True
        self.speech_queue = queue.Queue()
        self.display_inst = display_inst
        self.running = True

    def run(self):
        while self.running:
            # This calls the intermittent listening script safely in the background
            phrase = mic.listen_intermittently(interval_seconds=5, display_inst=self.display_inst)
            if phrase:
                self.speech_queue.put(phrase)

    def get_latest_speech(self):
        """Non-blocking check to see if a command was spoken."""
        try:
            return self.speech_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.running = False
