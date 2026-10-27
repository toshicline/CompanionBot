import json
import time
import random

import transcribe_audio as mic
import test_text_to_speech as tts

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

    time.sleep(2)

    return {
        "response":response,
        "intent":intent
    }

def routine_prompt(path_to_routine):

    routine = load_routine(path_to_routine)

    tts.speak(f"It's time to do your {routine["name"]} routine.")

    begin_routine = prompt("Are you ready to get started?")

    if begin_routine["intent"] == "affirmative":
        tts.speak(f"Ok, let's get started.")
    else:
        tts.speak(f"Ok. Let me know when you are ready to do your {routine["name"]} routine.")
        return None

    step_number = 1

    for step in routine["steps"]:

        while True:

            tts.speak(f"The {to_ordinal(step_number)} step is to {step["name"]} ")

            finished_with_step = prompt(f"Are you done with the task: {step["name"]}?")

            if (finished_with_step["intent"] == "affirmative"):
                tts.speak(encouragement())
                step_number += 1
                break
            elif (finished_with_step["intent"] == "unknown"):
                tts.speak("I didn't quite understand that.")
            else:
                tts.speak("Ok. I'll check back in a minute.")
                time.sleep(10)

    tts.speak(f"That's everything! {encouragement()}")
            



routine_prompt("./example_routine.json")
