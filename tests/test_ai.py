import os
import json
from google import genai
from google.genai import types

def main():
    config_path = os.path.expanduser("~/.config/dictate-whisper/config.json")
    if not os.path.exists(config_path):
        print(f"No se encontró archivo de configuración en {config_path}")
        return
        
    with open(config_path, "r") as f:
        config = json.load(f)
        
    api_key = config.get("api_key")
    if not api_key:
        print("No se encontró API Key en la configuración.")
        return
        
    model = config.get("model", "gemma-4-26b-a4b-it")
    temperature = config.get("llm_temperature", 0.7)
    thinking = config.get("llm_thinking", False)
    
    print(f"Probando configuración de IA:")
    print(f"  - Modelo: {model}")
    print(f"  - Temperatura: {temperature}")
    print(f"  - Pensamiento IA (Chain of Thought): {'Activado' if thinking else 'Desactivado'}")
    print("-" * 40)
    
    try:
        client = genai.Client(api_key=api_key)
        
        gen_config = types.GenerateContentConfig(
            temperature=temperature
        )
        if thinking:
            gen_config.thinking_config = types.ThinkingConfig(thinking_budget=-1)
            
        print("Enviando petición de prueba (generación en progreso)...")
        prompt = "¿Puedes explicar brevemente cómo funciona la gravedad?"
        print(f"Prompt: {prompt}")
        
        response = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=gen_config
        )
        
        print("-" * 40)
        print("Respuesta del modelo:")
        print(response.text)
        print("-" * 40)
        print("¡Prueba exitosa! Las configuraciones son válidas y el modelo responde correctamente.")
        
    except Exception as e:
        print("\n" + "=" * 40)
        print("ERROR DURANTE LA PRUEBA:")
        print(e)
        if "Thinking budget is not supported" in str(e):
            print("\nNota: El modelo actual no soporta el 'Modo Pensamiento'.")
            print("Si estás usando gemma-4 o modelos de la capa gratuita más básica, esto es esperado.")
            print("Desactiva el Modo Pensamiento en la configuración, o cambia a un modelo que lo soporte (ej. gemini-2.0-pro).")
        print("=" * 40)

if __name__ == "__main__":
    main()
