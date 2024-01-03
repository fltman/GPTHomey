# GPTHomey - A Night's Experiment with AI in Home Automation

I wanted to share a little project I hacked together tonight. It's a Python script that performs an interesting task - it listens to my voice and, when it detects silence, it records my speech into a WAV file. This is just the initial step.
The WAV file then goes to OpenAI's Whisper for transcription. Afterward, the transcribed text is processed by GPT-3.5-turbo to determine if I'm attempting to make a function call. If a function call is detected, it's sent to my Homey's API, which subsequently controls my Twinkly lights in the tree.
Practically, what does this mean? It allows for a unique interaction with my home automation system. I can now use any tone, any choice of words, and any language to command my home automation. This setup offers a new and interesting way to engage with smart home technologies.
