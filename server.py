from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
import tempfile
import os
from dotenv import load_dotenv
from groq import Groq

# Load the API key from your existing .env file
load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

app = FastAPI(title="Accessibility AI Backend")

class AIResponse(BaseModel):
    suggestion: str

@app.get("/")
def read_root():
    return {"status": "Server is running perfectly!"}

@app.post("/api/process-audio", response_model=AIResponse)
async def process_audio(audio_file: UploadFile = File(...)):
    """Receives an audio file, transcribes it, and generates a prompt."""
    try:
        # 1. Save the uploaded audio temporarily on the server
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(await audio_file.read())
            temp_filename = temp_audio.name

        # 2. Whisper: Speech to Text
        with open(temp_filename, "rb") as file:
            transcription = client.audio.transcriptions.create(
              file=(temp_filename, file.read()),
              model="whisper-large-v3",
              prompt="The audio is a clear voice speaking in English.",
              response_format="json",
            )

        user_text = transcription.text.strip()
        os.remove(temp_filename) # Clean up

        if not user_text:
            return {"suggestion": ""}

        # 3. Llama 3.1: Generate Professional Answer
        chat_completion = client.chat.completions.create(
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
        return {"suggestion": answer}

    except Exception as e:
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error processing AI.")