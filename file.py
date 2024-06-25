import openai
import pyttsx3
import pyaudio
import wave

client = openai.OpenAI(api_key='VOTRE_CLE_API_OPENAI')

def record_audio():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    RECORD_SECONDS = 5
    WAVE_OUTPUT_FILENAME = "output.wav"
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    print("Je vous écoute...")
    frames = [stream.read(CHUNK) for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS))]
    print("Enregistrement terminé.")
    stream.stop_stream()
    stream.close()
    p.terminate()
    wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    return WAVE_OUTPUT_FILENAME

def recognize_speech():
    audio_path = record_audio()
    with open(audio_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="fr"
        )
    return response.text

def speak(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()

def get_chatgpt_response(prompt):
    response = client.completions.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=150
    )
    return response.choices[0].text.strip()

def main():
    while True:
        user_input = recognize_speech()
        print(f"Texte reconnu: {user_input}")
        if user_input.lower() in ["arrêter", "stop", "quitter"]:
            speak("Au revoir!")
            break
        print(f"Requête à OpenAI : {user_input}")
        response = get_chatgpt_response(user_input)
        print(f"Réponse de ChatGPT: {response}")
        speak(response)

if __name__ == "__main__":
    main()
 
