import time
import threading
import json
import os

from display import RobotDisplay
from routine_prompting import routine_prompt
from transcribe_audio import listen_intermittently
from text_to_speech import speak


####################################################
#                  HELPER METHODS                  #
####################################################

def load_json(path):
    with open(path, "r") as file:
        return json.load(file)



####################################################
#                  ORCHESTRATOR                    #
####################################################

class RobotOrchestrator:

    def __init__(self,display: RobotDisplay):

        # Initialize display
        self.display = display

        # Initialize state machine
        self.current_state = "FOLLOWING"
        self.previous_state = "FOLLOWING"
        self.running = True

        # Initialize speech transcription
        self.user_speech = ""

        # Set up location
        self.current_location = "bedroom"

        # Load routines
        self.routines = [{
                    "path":f"./routines/{path}",
                    "routine":load_json(f"./routines/{path}")
                } 
                for path in os.listdir("routines/")
            ]



    def run_state_machine(self):
        print("[Orchestrator] Orchestrator state machine started.")

        while self.running:

            # Track change in state machine
            if self.current_state != self.previous_state:
                print(f"[Orchestrator] Change state from {self.previous_state} to {self.current_state}")



            ####################################################
            #                 FOLLOWING State                  #
            ####################################################
            if self.current_state == "FOLLOWING":

                # Intermittently listen for user to give commands
                self.user_speech = listen_intermittently(display_inst=self.display)

                # Take action based on user commands
                if "routine" in self.user_speech:
                    self.current_state = "PROMPTING"
                elif "end state machine" in self.user_speech:
                    display.close()

                time.sleep(1)


            ####################################################
            #                 NAVIGATING State                 #
            ####################################################
            elif self.current_state == "NAVIGATING":

                time.sleep(1)
                self.current_state = "FOLLOWING"



            ####################################################
            #                 PROMPTING State                  #
            ####################################################
            elif self.current_state == "PROMPTING":

                # Figure out what routine to do
                routine = self.find_routine(self.user_speech)

                if (routine == None):
                    speak("Sorry, I couldn't find a routine with that name.")
                else:
                    routine_prompt(routine["path"],display,self.navigate_to)

                self.current_state = "FOLLOWING"


            # Update previous state
            self.previous_state = self.current_state
            time.sleep(1)
            


    def find_routine(self,speech):

        speech = speech.lower().strip().replace(".","")

        for routine in self.routines:
            routine_name = routine["routine"]["name"].lower().strip()

            if routine_name in speech:
                return routine

        return None

    def get_location(self):
        return self.current_location

    def navigate_to(self,location):
        """Handles navigation and blocks until arrival for routine prompting
        
        Args:
            location (str): where to navigate

        Returns:
            None
        """

        print(f"[Orchestrator] Navigating to '{location}'...")
        self.display.show_navigating(location)

        time.sleep(3)

        print(f"[Orchestrator] Arrived at '{location}'.")

    def stop(self):
        self.running = False




if __name__ == "__main__":
    # Init display (UI)
    display = RobotDisplay()

    # Init orchestator
    orchestrator = RobotOrchestrator(display)

    # Assign orchestrator to display
    display.set_orchestrator(orchestrator)

    # Start orchestrator on background thread
    orchestrator_thread = threading.Thread(target=orchestrator.run_state_machine, daemon=True)
    orchestrator_thread.start()

    # Run tkinter UI on main thread
    display.run()