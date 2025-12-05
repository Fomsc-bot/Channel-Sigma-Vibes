#!/usr/bin/env python3
import os
import google.generativeai as genai

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in environment variables.")

    genai.configure(api_key=api_key)

    print("[*] Listing available models...")
    models = genai.list_models()

    if not models:
        print("[!] No models found. Your API key may not have access.")
    else:
        for m in models:
            print(f"- {m.name} (supports: {m.supported_generation_methods})")

if __name__ == "__main__":
    main()
