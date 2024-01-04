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


FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
RECORD_SECONDS = 60
OUTPUT_FILENAME = "output.wav"

CHUNK = int(RATE * 0.03)  # 30ms window
VAD_MODE = 1  # 0-3, 3 is the most aggressive
MIN_SPEECH_CHUNKS = 10


def get_devices():
	url = f"http://{homey_ip}/api/manager/devices/device/"
	headers = {"Authorization": f"Bearer {api_key}"}
	response = requests.get(url, headers=headers)
	
	if response.status_code == 200:
		devices = response.json()
		# Creating a dictionary with only the name and UUID of each device
		devices_info = {device_id: {'name': device_info.get('name', 'Unknown'), 'capabilities': device_info.get('capabilities', 'Unknown'),'device_id': device_id} 
						for device_id, device_info in devices.items()}
		return devices_info
	else:
		print("Failed to retrieve data:", response.status_code)
		return {}
	

def manage_device(device_id, capabilities):
	base_url = f"http://{homey_ip}/api/manager/devices/device/{device_id}/capability"
	headers = {"Authorization": f"Bearer {api_key}"}
	responses = {}
	
	for capability, value in capabilities.items():
		url = f"{base_url}/{capability}"
		payload = {"value": value}
		response = requests.put(url, headers=headers, json=payload)
		
		if response.status_code == 200:
			responses[capability] = f"Successfully set '{capability}' to '{value}'"
		else:
			responses[capability] = f"Failed to set '{capability}': {response.status_code}"
			
	return json.dumps(responses)

def add_user_message(message):
	if message:
		# Modify this to the new function definition
		my_function = {
			"type": "function",
			"function": {
				"name": "manage_device",
				"description": "Control device capabilities like on/off and dim",
				"parameters": {
					"type": "object",
					"properties": {
						"device_id": {
							"type": "string",
							"description": "The ID of the device",
						},
						"capabilities": {
							"type": "object",
							"description": "Capabilities and their values",
						}
					},
					"required": ["device_id", "capabilities"],
				},
			}
		}
		#print(messages)
		messages.append(
			{"role": "user", "content": message},
		)
		model = "gpt-4-1106-preview"
		
		chat_completion = client.chat.completions.create(
			model=model, 
			messages=messages,
			temperature=0.7,
			tools=[my_function],
			tool_choice="auto"
		)
		
		reply = chat_completion.choices[0].message.content
		
		if reply:
			messages.append({"role": "assistant", "content": reply})
			
		response_message = chat_completion.choices[0].message
		
		tool_calls = response_message.tool_calls
		
		if tool_calls:
			
			available_functions = {
				"manage_device": manage_device,
			}  
			
			messages.append(response_message)
			
			for tool_call in tool_calls:
				function_name = tool_call.function.name
				function_to_call = available_functions[function_name]
				function_args = json.loads(tool_call.function.arguments)
				print("Function args:", function_args)
				
				if 'capabilities' in function_args and isinstance(function_args['capabilities'], dict):
					function_response = function_to_call(
						device_id=function_args.get("device_id"),    
						capabilities=function_args.get("capabilities")
					)
				else:
					function_response = "Error: 'capabilities' not found or not a dictionary in function arguments"
					
				messages.append(
					{
						"tool_call_id": tool_call.id,
						"role": "tool",
						"name": function_name,
						"content": function_response,
					}
				)
				
			second_response = client.chat.completions.create(
				model="gpt-4-1106-preview",
				messages=messages,
			)  # get a new response from the model where it can see the function response
			
			reply = second_response.choices[0].message.content
			
			if reply:
				messages.append({"role": "assistant", "content": reply})	
					
		return reply
	else:
		return "huh?"
	
	
	
def record_audio():
	vad = webrtcvad.Vad(VAD_MODE)
	audio = pyaudio.PyAudio()
	
	while True:  # Add an outer loop to restart recording if needed
		# Start Recording
		stream = audio.open(format=FORMAT, channels=CHANNELS,
							rate=RATE, input=True,
							frames_per_buffer=CHUNK)
		print("Listening...")
	
		frames = []
		num_silent_chunks = 0
		num_speech_chunks = 0
	
		while True:
			# Read audio chunk
			data = stream.read(CHUNK)
			frames.append(data)
			
			# Check if chunk contains speech
			is_speech = vad.is_speech(data, RATE)
			
			if is_speech:
				print("Speaking...")
				num_silent_chunks = 0  # reset the counter of silent chunks
				num_speech_chunks += 1  # increment the speech chunk counter
			else:
				print("Silence...")
				num_silent_chunks += 1  # increment the counter of silent chunks
				
				# [Optional] Stop listening if only silence is detected for a certain number of chunks
				if num_silent_chunks > 30:  # for example, stop if 300ms of silence is detected
					break
			
			# [Optional] Stop listening after a certain time of speaking
			#if num_speech_chunks > int(RECORD_SECONDS * (1000 / (CHUNK / RATE))):
				#break
			
		# Stop Recording
		stream.stop_stream()
		stream.close()
	
		# Check if the recording has enough speech chunks
		if num_speech_chunks >= MIN_SPEECH_CHUNKS:
			print("Finished recording")
			break  # exit the outer loop if the recording is valid
		else:
			print("Not enough speech, starting over...")
			frames.clear()  # clear frames to start over
			
	# Save the audio file
	audio.terminate()
	with wave.open(OUTPUT_FILENAME, 'wb') as wf:
		wf.setnchannels(CHANNELS)
		wf.setsampwidth(audio.get_sample_size(FORMAT))
		wf.setframerate(RATE)
		wf.writeframes(b''.join(frames))
		
def transcribe_audio(file_path):
	audio_file = open(file_path, "rb")
	transcript = client.audio.transcriptions.create(
		model="whisper-1",
		file=audio_file
	)
	
	return transcript.text

def get_user_input():
	#input("Press Enter to start recording...")
	record_audio()
	
	transcription = transcribe_audio("output.wav")
	return transcription

devices = get_devices()
#print (devices)

messages = [{"role": "system", "content": f"You are my helpful assistant. Those are my devices and their devices_id: {devices}. Here are the available capabilities and their definitions: capabilities: ['onoff', 'light_saturation', 'light_temperature', 'dim', 'light_hue', 'light_mode', 'has_movie_support', 'has_white_support', 'is_retail'] capabilitiesObj: {{'is_retail': {{'id': 'is_retail', 'type': 'boolean', 'iconObj': None, 'title': 'Is a retail device.', 'getable': False, 'setable': False, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'value': None, 'lastUpdated': 1703211557098}}, 'has_white_support': {{'id': 'has_white_support', 'type': 'boolean', 'iconObj': None, 'title': 'Supports setting true white through api.', 'getable': False, 'setable': False, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'value': None, 'lastUpdated': 1703211556886}}, 'has_movie_support': {{'id': 'has_movie_support', 'type': 'boolean', 'iconObj': None, 'title': 'Supports setting effects through api.', 'getable': False, 'setable': False, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'value': None, 'lastUpdated': 1703211556796}}, 'light_mode': {{'id': 'light_mode', 'type': 'enum', 'iconObj': None, 'title': 'Light mode', 'getable': True, 'setable': True, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'values': [{{'id': 'color', 'title': 'Color'}}, {{'id': 'temperature', 'title': 'Temperature'}}], 'value': 'color', 'lastUpdated': 1689731216765}}, 'light_hue': {{'id': 'light_hue', 'type': 'number', 'iconObj': None, 'title': 'Hue', 'getable': True, 'setable': True, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'min': 0, 'max': 1, 'units': None, 'decimals': 2, 'value': 0, 'lastUpdated': 1689368433396}}, 'dim': {{'id': 'dim', 'type': 'number', 'iconObj': None, 'title': 'Dim level', 'getable': True, 'setable': True, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'min': 0, 'max': 1, 'units': '%', 'decimals': 2, 'value': 0, 'lastUpdated': 1704093170237}}, 'light_temperature': {{'id': 'light_temperature', 'type': 'number', 'iconObj': None, 'title': 'Color temperature', 'getable': True, 'setable': True, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'min': 0, 'max': 1, 'units': None, 'decimals': 2, 'value': 0, 'lastUpdated': 1689540493954}}, 'light_saturation': {{'id': 'light_saturation', 'type': 'number', 'iconObj': None, 'title': 'Color saturation', 'getable': True, 'setable': True, 'insightsTitleTrue': None, 'insightsTitleFalse': None, 'min': 0, 'max': 1, 'units': None, 'decimals': 2, 'value': 0, 'lastUpdated': 1689368433401}}, 'onoff': {{'id': 'onoff', 'type': 'boolean', 'iconObj': None, 'title': 'Turned on', 'getable': True, 'setable': True, 'insights': True, 'insightsTitleTrue': 'Turned on', 'insightsTitleFalse': 'Turned off', 'value': False, 'lastUpdated': 1704093170241}}}}. This is what a capabilities object may look like: capabilities = {{'onoff': True, 'dim': 0.3}}" }]


while True:
	command = get_user_input()
	print (command)
	print(add_user_message(command))
