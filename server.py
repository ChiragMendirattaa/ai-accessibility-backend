from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import tempfile
import os
from dotenv import load_dotenv
from groq import Groq

# Load the API keys from your existing .env file
load_dotenv()

# 1. Initialize a list of available AI clients (Primary + Fallbacks)
clients = []
primary_key = os.environ.get("GROQ_API_KEY")
fallback_key = os.environ.get("GROQ_FALLBACK_API_KEY")

if primary_key:
    clients.append(Groq(api_key=primary_key))
if fallback_key:
    clients.append(Groq(api_key=fallback_key))

if not clients:
    raise ValueError("No Groq API keys found. Please set GROQ_API_KEY.")

app = FastAPI(title="Accessibility AI Backend")

class AIResponse(BaseModel):
    suggestion: str

@app.get("/")
def read_root():
    return {"status": "Server is running perfectly with failover support!"}

@app.post("/api/process-audio", response_model=AIResponse)
async def process_audio(audio_file: UploadFile = File(...)):
    """Receives an audio file, transcribes it, and generates a prompt with automatic API failover."""
    try:
        # Save the uploaded audio temporarily on the server
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await audio_file.read())
            temp_filename = temp_audio.name

        # Read the file bytes once so we can reuse them if a fallback is needed
        with open(temp_filename, "rb") as file:
            audio_bytes = file.read()

        answer = ""

        # 2. The Failover Loop (Tries Primary, then Fallback if needed)
        for attempt, current_client in enumerate(clients):
            try:
                # Whisper: Speech to Text
                transcription = current_client.audio.transcriptions.create(
                  file=(temp_filename, audio_bytes),
                  model="whisper-large-v3",
                  prompt="The audio is a clear voice speaking in English.",
                  response_format="json",
                )

                user_text = transcription.text.strip()

                if not user_text:
                    os.remove(temp_filename)
                    return {"suggestion": ""}

                # Llama 3.1: Generate Professional Answer
                chat_completion = current_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an expert interview coach. The user is in a live job interview. Based on the transcribed audio, provide a highly professional, structured, and impressive answer that the user can speak directly. Keep it conversational, impactful, and between 2 to 3 sentences. Do not use introductory filler like 'Here is your answer'."
                        },
                        {
                            "role": "user",
                            "content": f"The interviewer just said: '{user_text}'"
                        }
                    ],
                    model="llama-3.1-8b-instant",
                    temperature=0.6,
                    max_tokens=200
                )

                answer = chat_completion.choices[0].message.content

                # If we made it here without an exception, the API call succeeded! Break the loop.
                break

            except Exception as e:
                print(f"Groq API Error on client {attempt + 1}: {e}")
                # If this was the last client in our list, raise the error so it doesn't fail silently
                if attempt == len(clients) - 1:
                    os.remove(temp_filename)
                    raise HTTPException(status_code=500, detail="All AI providers failed.")

        # Clean up the audio file from the server disk
        os.remove(temp_filename)
        return {"suggestion": answer}

    except Exception as e:
        print(f"Server Error: {e}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        raise HTTPException(status_code=500, detail="Internal Server Error processing AI.")