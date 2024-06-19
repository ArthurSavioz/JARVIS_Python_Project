import openai
import speech_recognition as sr
import pyttsx3
import requests
import os
import time
import logging
from google.cloud import speech
from typing import List, Dict
import json
from datetime import datetime
from collections import defaultdict

# Configuration de l'API OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initialisation du synthétiseur vocal
engine = pyttsx3.init()

# Historique de la conversation pour maintenir le contexte
conversation_history: List[Dict[str, str]] = []
unrecognized_commands = defaultdict(int)  # Pour l'apprentissage continu

# Configuration des logs pour le debug et les erreurs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constantes pour la configuration
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
HA_URL = "http://homeassistant.local:8123/api"
HA_TOKEN = os.getenv('HA_ACCESS_TOKEN')
RESET_TIME = 300  # Réinitialiser le contexte après 5 minutes d'inactivité
LOG_FILE = 'jarvis_interactions.log'
KNOWLEDGE_FILE = 'jarvis_knowledge.json'

def recognize_speech_google(audio_data: sr.AudioData) -> str:
    """Utilise Google Cloud Speech-to-Text pour reconnaître la parole."""
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_data.get_wav_data())
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="fr-FR",
    )
    response = client.recognize(config=config, audio=audio)
    return response.results[0].alternatives[0].transcript

def chat_with_openai(prompt: str) -> str:
    """Communique avec OpenAI pour générer une réponse basée sur l'historique de conversation."""
    conversation_history.append({"role": "user", "content": prompt})
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=conversation_history[-10:],  # Limiter à 10 derniers échanges pour optimiser les coûts
        max_tokens=150
    )
    reply = response.choices[0].message['content']
    conversation_history.append({"role": "assistant", "content": reply})
    return reply.strip()

def identify_command(command: str) -> str:
    """Identifie le type de commande à partir de l'input utilisateur."""
    commands = load_knowledge()
    for key in commands:
        if key in command:
            return commands[key]
    return "chat"

def load_knowledge() -> Dict[str, str]:
    """Charge les connaissances de Jarvis à partir d'un fichier."""
    if os.path.exists(KNOWLEDGE_FILE):
        with open(KNOWLEDGE_FILE, 'r') as file:
            return json.load(file)
    return {
        "musique": "play_music",
        "télévision": "turn_on_tv",
        "tv": "turn_on_tv",
        "lumière": "control_light",
        "température": "control_temperature",
        "volume": "adjust_volume",
        "réinitialiser": "reset_context"
    }

def save_knowledge(knowledge: Dict[str, str]) -> None:
    """Sauvegarde les connaissances de Jarvis dans un fichier."""
    with open(KNOWLEDGE_FILE, 'w') as file:
        json.dump(knowledge, file)

def handle_command(command_type: str, command: str) -> str:
    """Gère l'exécution des commandes identifiées."""
    def control_device(service: str, entity_id: str, payload: dict = {}) -> str:
        """Envoie des commandes à Home Assistant."""
        try:
            response = requests.post(f"{HA_URL}/services/{service}", json={
                "entity_id": entity_id, **payload
            }, headers={"Authorization": f"Bearer {HA_TOKEN}"})
            response.raise_for_status()
            return f"{service} exécuté avec succès."
        except requests.RequestException as e:
            logger.error(f"Erreur lors de l'exécution de {service}: {e}")
            return f"Erreur lors de l'exécution de {service}: {e}"

    handlers = {
        "play_music": lambda: control_device("media_player/play_media", "media_player.spotify", {
            "media_content_id": "spotify:track:TRACK_ID", "media_content_type": "music"
        }),
        "turn_on_tv": lambda: control_device("remote/turn_on", "remote.living_room_tv"),
        "control_light": lambda: control_device(f"light/turn_{'on' if 'allume' in command else 'off'}", "light.living_room"),
        "control_temperature": lambda: control_device("climate/set_temperature", "climate.living_room", {
            "temperature": int(command.split()[-1])
        }),
        "adjust_volume": lambda: adjust_volume(command),
        "reset_context": lambda: reset_context(),
        "chat": lambda: chat_with_openai(command)
    }

    result = handlers.get(command_type, lambda: "Commande non reconnue.")()
    if result == "Commande non reconnue.":
        unrecognized_commands[command] += 1  # Apprentissage continu
        log_interaction(command, result)
    return result

def adjust_volume(command: str) -> str:
    """Ajuste le volume du synthétiseur vocal."""
    try:
        volume_level = int(command.split()[-1])
        if 0 <= volume_level <= 100:
            engine.setProperty('volume', volume_level / 100.0)
            return f"Volume ajusté à {volume_level}%."
        else:
            return "Veuillez spécifier un niveau de volume entre 0 et 100."
    except ValueError:
        return "Commande de volume non reconnue. Veuillez spécifier un niveau de volume entre 0 et 100."

def reset_context() -> str:
    """Réinitialise l'historique de la conversation."""
    conversation_history.clear()
    return "Contexte de la conversation réinitialisé."

def natural_language_processing(text: str) -> str:
    """Analyse le texte pour comprendre les intentions et améliorer les réponses."""
    # Placeholder pour un traitement NLP plus avancé
    return text

def log_interaction(command: str, response: str) -> None:
    """Enregistre les interactions dans un fichier log pour analyse ultérieure."""
    with open(LOG_FILE, 'a') as file:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "response": response
        }
        file.write(json.dumps(log_entry) + "\n")

def analyze_interactions() -> None:
    """Analyse les interactions enregistrées pour améliorer Jarvis."""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as file:
            logs = [json.loads(line) for line in file.readlines()]

        knowledge = load_knowledge()
        for log in logs:
            if log['response'] == "Commande non reconnue.":
                command_parts = log['command'].split()
                if len(command_parts) > 1:
                    key = command_parts[0]
                    action = command_parts[1]
                    if key not in knowledge:
                        knowledge[key] = action
        save_knowledge(knowledge)

def listen_and_respond() -> None:
    """Écoute les commandes vocales et y répond."""
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    last_interaction_time = time.time()

    while True:
        try:
            with microphone as source:
                recognizer.adjust_for_ambient_noise(source)
                print("Dites quelque chose...")
                audio = recognizer.listen(source)

            command = recognize_speech_google(audio)
            print(f"Vous avez dit : {command}")

            if "bonjour jarvis" in command.lower():
                command = natural_language_processing(command)  # NLP pour analyse
                command_type = identify_command(command)
                response = handle_command(command_type, command)
                print(f"Jarvis: {response}")
                engine.say(response)
                engine.runAndWait()

            if time.time() - last_interaction_time > RESET_TIME:
                reset_context()
                print("Contexte de la conversation réinitialisé en raison de l'inactivité.")
            last_interaction_time = time.time()

        except sr.UnknownValueError:
            logger.warning("Je n'ai pas compris ce que vous avez dit.")
            engine.say("Je n'ai pas compris ce que vous avez dit.")
            engine.runAndWait()
        except sr.RequestError as e:
            logger.error(f"Erreur de reconnaissance vocale: {e}")
            engine.say(f"Erreur de reconnaissance vocale: {e}")
            engine.runAndWait()
        except Exception as e:
            logger.error(f"Une erreur s'est produite: {e}")
            engine.say(f"Une erreur s'est produite: {e}")
            engine.runAndWait()

if __name__ == "__main__":
    analyze_interactions()  # Analyser les interactions avant de démarrer
    listen_and_respond()
