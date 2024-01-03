#!/usr/bin/env python3
import pyaudio
from openai import OpenAI
import json
import requests
import collections
import webrtcvad
import time
import wave

# Initialize OpenAI client
client = OpenAI()

# Homey API credentials
homey_ip = "192.168.0.108"
api_key = "YOUR_API_KEY"  # Replace with your actual API key

# Audio recording settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 60
OUTPUT_FILENAME = "output.wav"

# Voice Activity Detection (VAD) settings
CHUNK = int(RATE * 0.03)  # 30ms window
VAD_MODE = 1  # 0-3, 3 is the most aggressive
MIN_SPEECH_CHUNKS = 10

# Function to get devices from Homey API
def get_devices():
	url = f"http://{homey_ip}/api/manager/devices/device/"
	headers = {"Authorization": f"Bearer {api_key}"}
	response = requests.get(url, headers=headers)
	
	if response.status_code == 200:
		devices = response.json()
		# Return a dictionary with only the name and device ID of each device
		return {device_id: {'name': device_info.get('name', 'Unknown'), 
		                    'device_id': device_id} 
		        for device_id, device_info in devices.items()}
	else:
		print("Failed to retrieve data:", response.status_code)
		return {}
	
# Function to manage a device
def manage_device(device_id, value):
	url = f"http://{homey_ip}/api/manager/devices/device/{device_id}/capability/onoff"
	headers = {"Authorization": f"Bearer {api_key}"}
	payload = {"value": value}
	response = requests.put(url, headers=headers, json=payload)
	
	if response.status_code == 200:
		return json.dumps({"status": "Success", "message": f"Action performed on device '{device_id}'"})
	else:
		return json.dumps({"status": "Failed", "message": f"Error {response.status_code}"})
	
# Function to process user messages and call functions
def add_user_message(message):
	if message:
		# Define the function to be used in GPT-3.5-turbo
		my_function = {
			"type": "function",
			"function": {
				"name": "manage_device",
				"description": "Control the lights in the tree",
				"parameters": {
					"type": "object",
					"properties": {
						"device_id": {
							"type": "string",
							"description": "The ID of my device",
						},
						"value": {
							"type": "boolean",
							"description": "Turns the light on or off",
						}
					},
					"required": ["device_id", "value"],
				},
			}
		}
		
		messages.append({"role": "user", "content": message})
		
		# Get a response from GPT-3.5-turbo
		chat_completion = client.chat.completions.create(
			model="gpt-3.5-turbo-1106", 
			messages=messages,
			temperature=0.7,
			tools=[my_function],
			tool_choice="auto"
		)
		
		reply = chat_completion.choices[0].message.content
		messages.append({"role": "assistant", "content": reply})
		
		# Process any tool calls in the response
		tool_calls = chat_completion.choices[0].message.tool_calls
		if tool_calls:
			available_functions = {"manage_device": manage_device}
			messages.append(chat_completion.choices[0].message)
			
			for tool_call in tool_calls:
				function_name = tool_call.function.name
				function_to_call = available_functions[function_name]
				function_args = json.loads(tool_call.function.arguments)
				function_response = function_to_call(**function_args)
				messages.append({
					"tool_call_id": tool_call.id,
					"role": "tool",
					"name": function_name,
					"content": function_response,
				})
				
				# Get a new response from the model considering the function response
				second_response = client.chat.completions.create(
					model="gpt-3.5-turbo-1106",
					messages=messages,
				)
				reply = second_response.choices[0].message.content
				if reply:
					messages.append({"role": "assistant", "content": reply})	
					
		return reply
	else:
		return "huh?"

# Function to record audio using Voice Activity Detection (VAD)
def record_audio():
	vad = webrtcvad.Vad(VAD_MODE)
	audio = pyaudio.PyAudio()
	
	while True:
		stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
		print("Listening...")

		frames = []
		num_silent_chunks = 0
		num_speech_chunks = 0

		while True:
			data = stream.read(CHUNK)
			frames.append(data)
			
			is_speech = vad.is_speech(data, RATE)
			
			if is_speech:
				num_silent_chunks = 0
				num_speech_chunks += 1
			else:
				num_silent_chunks += 1
				if num_silent_chunks > 30:  # Stop if 300ms of silence is detected
					break

		stream.stop_stream()
		stream.close()

		if num_speech_chunks >= MIN_SPEECH_CHUNKS:
			break
		else:
			frames.clear()

	audio.terminate()
	with wave.open(OUTPUT_FILENAME, 'wb') as wf:
		wf.setnchannels(CHANNELS)
		wf.setsampwidth(audio.get_sample_size(FORMAT))
		wf.setframerate(RATE)
		wf.writeframes(b''.join(frames))
		
# Function to transcribe audio using OpenAI's Whisper
def transcribe_audio(file_path):
	with open(file_path, "rb") as audio_file:
		transcript = client.audio.transcriptions.create(
			model="whisper-1",
			file=audio_file
		)
	
	return transcript.text

# Function to get user input through audio recording and transcription
def get_user_input():
	record_audio()
	transcription = transcribe_audio("output.wav")
	return transcription

# Retrieve and store device information
devices = get_devices()

# Initialize message history for conversation with GPT-3.5-turbo
messages = [{"role": "system", "content": f"You are my helpful assistant. These are my devices and their IDs: {devices}"}]

# Main loop to process voice commands
while True:
	command = get_user_input()
	print(command)
	print(add_user_message(command))
