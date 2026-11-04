import json
import time
import random

import transcribe_audio as mic
import text_to_speech as tts

def load_routine(path):
    with open(path, "r") as file:
        return json.load(file)

def to_ordinal(n):
    """Convert an integer to its ordinal string representation.

    Args:
        n (int): The number to convert

    Returns:
        str: The number with its ordinal suffix (e.g., '1st', '2nd', '3rd')
    """
    # Special case for the teens (11th, 12th, 13th) which always end in 'th'
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        # Map last digit to the correct suffix
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        
    return f"{n}{suffix}"

def encouragement():
    """Return an encouraging phrase like 'Nice job' or 'Awesome'

    Returns:
        str: encouraging phrase
    """

    encouraging_phrases = ["Nice job!","Great!","Awesome!","Fantastic!","Good!"]

    return random.choice(encouraging_phrases)


def classify_intent(text):
    """Classify a response as affirmative, negative, or unknown based on keywords

    Args:
        text (str): the text to classify

    Returns:
        str: affirmative, negative, or unknown
    """

    affirmative_keywords = [
        "yes","yeah","yep","done","finished","got it","okay","ok","sure"
    ]
    negative_keywords = [
        "no","nope","wait","stop","cancel"
    ]

    for word in negative_keywords:
        if word in text:
            return "negative"

    for word in affirmative_keywords:
        if word in text:
            return "affirmative"

    return "unknown"


def prompt(prompt_text):
    """Ask a question or prompt the user, return the response and whether or not it contains the desired response

    Args:
        prompt_text (str): The spoken prompt the robot will give
    
    Returns:
        dict:
            {
                "response": the user's response to the prompt
                "intent": affirmative, negative, unknown
            }
    """

    tts.speak(prompt_text)
    response = mic.listen().lower().strip()

    intent = classify_intent(response)

    print(f"User> {response}")

    return {
        "response":response,
        "intent":intent
    }

def routine_prompt(path_to_routine):

    # Load the routine JSON
    routine = load_routine(path_to_routine)

    # Prompt the user to start
    # Tell the orchestrator to show the routine title screen here
    tts.speak(f"It's time to do your {routine["name"]} routine.")
    begin_routine = prompt("Are you ready to get started?")

    if begin_routine["intent"] == "affirmative":
        tts.speak(f"Ok, let's get started.")
    else:
        tts.speak(f"Ok. Let me know when you are ready to do your {routine["name"]} routine.")
        return None

    # Routine steps loop
    step_number = 1
    while True:

        # Exit steps loop
        if step_number > len(routine["steps"]):
            break

        step = routine["steps"][step_number-1]

        # State the routine step
        tts.speak(f"The {to_ordinal(step_number)} step is to {step["name"]} ")

        # Navigate to room if necessary
        # Tell the orchestrator script to tell it to navigate, then return here

        # Confirm task start
        tts.speak(f"Go ahead and get started with the task: {step["name"].lower()}")

        # Reminder / Listening Loop
        reminder_interval = step["reminder_interval_s"]
        last_reminder_time = time.time()
        step_completed = False

        while not step_completed:
            current_time = time.time()

            # Check to see if a reminder should be given
            if (current_time - last_reminder_time) >= reminder_interval:
                tts.speak(f"Reminder that you should be working on the task: {step["name"].lower()}.")
                last_reminder_time = time.time()

            # Listen for user to announce completion of task
            phrase = mic.listen(max_wait_seconds=5,silent=True)

            if phrase != "":
                print(f"Heard user: {phrase}")
                if classify_intent(phrase) == "affirmative":
                    tts.speak(encouragement())
                    step_completed = True
                    break

        step_number += 1

    tts.speak(f"That's everything! {encouragement()}")
            

routine_prompt("./example_routine.json")
