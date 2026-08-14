import os
import json

DEFAULT_LANG = "en"

TRANSLATIONS = {
    "en": {
        "ready": "Ready ({})",
        "recording": "Recording...",
        "paused": "Paused",
        "transcribing": "Transcribing...",
        "cleaning": "Cleaning text...",
        "processing": "Processing...",
        "ai_enabled": "AI: Enabled",
        "ai_disabled": "AI: Disabled",
        "autosend_enabled": "Auto-Send: Enabled",
        "autosend_disabled": "Auto-Send: Disabled",
        "autopause_enabled": "Auto-Pause Media: Enabled",
        "autopause_disabled": "Auto-Pause Media: Disabled",
        "bubble_visible": "Bubble: Visible",
        "bubble_hidden": "Bubble: Hidden",
        "error": "Error: {}",
        "copied": "Copied to clipboard",
        "quit": "Quit",
        "settings": "Settings",
        
        "close": "Close",
        "copy_clipboard": "Copy to clipboard",
        "insert_text": "Insert (depends on config)",
        "loading_model": "Loading model...",
        "loading_model_param": "Loading {size}...",
        "whisper_model": "Whisper Model",
        "auto_send": "Auto-Send (Enter)",
        "ai_cleanup": "AI Cleaning",
        "opendeck_installed": "✅ OpenDeck: Installed",
        "opendeck_not_installed": "❌ OpenDeck: Not Installed",
        "error_opening_config": "Could not open settings.",
        "opendeck": "OpenDeck",
        "opendeck_installed_success": "OpenDeck plugin installed successfully.",
        "error_plugin_not_found": "Source plugin not found.",
        "error_whisper": "Whisper Error",
        "error_loading_model": "Error loading model",

        "settings_title": "Settings - OpenDictate",
        "tab_general": "General",
        "tab_apps": "Applications",
        "tab_ai": "AI & Models",
        "tab_models": "Model Manager",
        "tab_advanced": "Advanced",
        
        "ui_language": "UI Language:",
        "transcription_language": "Transcription Language:",
        "transcription_auto": "Automatic",
        
        "lbl_autosend": "Auto-send on completion",
        "lbl_realtime": "Real-time Chunk Analysis",
        "realtime_enabled": "Real-time: Enabled",
        "realtime_disabled": "Real-time: Disabled",
        "lbl_ai_enabled": "AI Cleanup and Formatting",
        "lbl_hide_bubble": "Hide Text Bubble",
        "lbl_auto_pause": "Auto-pause Media",
        "lbl_autostart": "Start with System",
        "lbl_notifications": "Show System Notifications",
        "lbl_restore_focus": "Restore window focus before pasting",
        "lbl_vad": "VAD Filter (Anti-noise)",
        
        "lbl_chunk_stride": "Chunk Stride (sec):",
        "lbl_chunk_overlap": "Chunk Overlap (sec):",
        "lbl_chunk_tolerance": "Overlap Tolerance (sec):",
        
        "btn_save_general": "Save General Settings",
        "btn_save_ai": "Save AI Settings",
        "btn_save_adv": "Save Advanced Settings",
        
        "lbl_provider": "API Provider:",
        "lbl_api_key": "API Key:",
        "lbl_model": "Model (Gemini):",
        "lbl_sys_prompt": "System Prompt:",
        "lbl_llm_timeout": "LLM Timeout (s):",
        "lbl_llm_temp": "LLM Temperature:",
        "lbl_llm_thinking": "Enable AI Thinking Mode (Chain of Thought):",
        
        "lbl_whisper_model": "Whisper Model:",
        "lbl_beam": "Precision (Beam Size):",
        "lbl_temp": "Temperature:",
        
        "lbl_app_select": "Select an application",
        "lbl_vision": "Enable Vision (Screen analysis)",
        "lbl_app_class": "Window Class Name (e.g. google-chrome):",
        "btn_add_rule": "Add / Update Rule",
        "btn_delete": "Delete",
        
        "msg_saved_title": "Saved",
        "msg_saved_general": "General settings saved successfully.",
        "msg_saved_ai": "AI settings saved successfully.",
        "msg_saved_adv": "Advanced settings saved successfully.",
        "msg_rule_added": "Rule for {} saved successfully.",
        "msg_rule_deleted": "Rule for {} deleted.",
        "msg_select_app": "Select an application",
        
        "model_downloaded": "✅ Downloaded",
        "model_not_downloaded": "❌ Not downloaded",
        "btn_activate": "Activate",
        "active_model": " (Active)"
    },
    "es": {
        "ready": "Listo ({})",
        "recording": "Grabando...",
        "paused": "Pausado",
        "transcribing": "Transcribiendo...",
        "cleaning": "Limpiando texto...",
        "processing": "Procesando...",
        "ai_enabled": "IA: Activada",
        "ai_disabled": "IA: Desactivada",
        "autosend_enabled": "Auto-Enviar: Activado",
        "autosend_disabled": "Auto-Enviar: Desactivado",
        "autopause_enabled": "Auto-Pausa Medios: Activada",
        "autopause_disabled": "Auto-Pausa Medios: Desactivada",
        "bubble_visible": "Burbuja: Visible",
        "bubble_hidden": "Burbuja: Oculta",
        "error": "Error: {}",
        "copied": "Copiado al portapapeles",
        "quit": "Salir",
        "settings": "Configuración",

        "close": "Cerrar",
        "copy_clipboard": "Copiar al portapapeles",
        "insert_text": "Insertar",
        "loading_model": "Cargando modelo...",
        "loading_model_param": "Cargando {size}...",
        "whisper_model": "Modelo Whisper",
        "auto_send": "Enviar Automático (Enter)",
        "ai_cleanup": "Limpieza con IA",
        "opendeck_installed": "✅ OpenDeck: Instalado",
        "opendeck_not_installed": "❌ OpenDeck: No Instalado",
        "error_opening_config": "No se pudo abrir la configuración.",
        "opendeck": "OpenDeck",
        "opendeck_installed_success": "Plugin de OpenDeck instalado exitosamente.",
        "error_plugin_not_found": "No se encontró el plugin fuente.",
        "error_whisper": "Error de Whisper",
        "error_loading_model": "Error cargando modelo",

        "settings_title": "Configuración - OpenDictate",
        "tab_general": "General",
        "tab_apps": "Aplicaciones",
        "tab_ai": "IA y Modelos",
        "tab_models": "Gestor de Modelos",
        "tab_advanced": "Avanzado",

        "ui_language": "Idioma de la interfaz:",
        "transcription_language": "Idioma de transcripción:",
        "transcription_auto": "Automático",

        "lbl_autosend": "Auto-enviar al transcribir",
        "lbl_realtime": "Análisis en tiempo real (Chunks)",
        "realtime_enabled": "Tiempo Real: Activado",
        "realtime_disabled": "Tiempo Real: Desactivado",
        "lbl_ai_enabled": "Limpieza y Formateo con IA",
        "lbl_hide_bubble": "Ocultar Burbuja de Texto",
        "lbl_auto_pause": "Auto-pausar Multimedia",
        "lbl_autostart": "Iniciar con el Sistema",
        "lbl_notifications": "Mostrar Notificaciones del Sistema",
        "lbl_restore_focus": "Restaurar foco de ventana antes de pegar",
        "lbl_vad": "Filtro VAD (Anti-ruido)",
        
        "lbl_chunk_stride": "Avance del chunk (seg):",
        "lbl_chunk_overlap": "Superposición del chunk (seg):",
        "lbl_chunk_tolerance": "Tolerancia de superposición (seg):",

        "btn_save_general": "Guardar Configuración General",
        "btn_save_ai": "Guardar Configuración de IA",
        "btn_save_adv": "Guardar Configuración Avanzada",

        "lbl_provider": "Proveedor API:",
        "lbl_api_key": "API Key:",
        "lbl_model": "Modelo (Gemini):",
        "lbl_sys_prompt": "Prompt del Sistema:",
        "lbl_llm_timeout": "Tiempo de espera LLM (s):",
        "lbl_llm_temp": "Temperatura LLM:",
        "lbl_llm_thinking": "Activar Modo Pensamiento (Chain of Thought):",

        "lbl_whisper_model": "Modelo de Whisper:",
        "lbl_vad": "Filtro VAD (Ignorar silencios):",
        "lbl_beam": "Precisión (Beam Size):",
        "lbl_temp": "Temperatura:",

        "lbl_app_select": "Selecciona una aplicación",
        "lbl_vision": "Activar Visión (Analizar pantalla)",
        "lbl_app_class": "Nombre de la Ventana (ej. google-chrome):",
        "btn_add_rule": "Añadir / Actualizar Regla",
        "btn_delete": "Eliminar",

        "msg_saved_title": "Guardado",
        "msg_saved_general": "Configuración general guardada exitosamente.",
        "msg_saved_ai": "Configuración de IA guardada exitosamente.",
        "msg_saved_adv": "Configuración avanzada guardada exitosamente.",
        "msg_rule_added": "Regla para {} guardada exitosamente.",
        "msg_rule_deleted": "Regla para {} eliminada.",
        "msg_select_app": "Selecciona una aplicación",
        
        "model_downloaded": "✅ Descargado",
        "model_not_downloaded": "❌ No descargado",
        "btn_activate": "Activar",
        "active_model": " (Activo)"
    },
    "de": {
        "ready": "Bereit ({})",
        "recording": "Aufnahme...",
        "paused": "Pausiert",
        "transcribing": "Transkribieren...",
        "cleaning": "Text bereinigen...",
        "processing": "Verarbeitung...",
        "ai_enabled": "KI: Aktiviert",
        "ai_disabled": "KI: Deaktiviert",
        "autosend_enabled": "Auto-Senden: Aktiviert",
        "autosend_disabled": "Auto-Senden: Deaktiviert",
        "autopause_enabled": "Auto-Pause Medien: Aktiviert",
        "autopause_disabled": "Auto-Pause Medien: Deaktiviert",
        "bubble_visible": "Blase: Sichtbar",
        "bubble_hidden": "Blase: Versteckt",
        "error": "Fehler: {}",
        "copied": "In die Zwischenablage kopiert",
        "quit": "Beenden",
        "settings": "Einstellungen",
        
        "close": "Schließen",
        "copy_clipboard": "In die Zwischenablage kopieren",
        "insert_text": "Einfügen",
        "loading_model": "Modell wird geladen...",
        "loading_model_param": "{size} wird geladen...",
        "whisper_model": "Whisper-Modell",
        "auto_send": "Auto-Senden (Enter)",
        "ai_cleanup": "KI-Bereinigung",
        "opendeck_installed": "✅ OpenDeck: Installiert",
        "opendeck_not_installed": "❌ OpenDeck: Nicht installiert",
        "error_opening_config": "Einstellungen konnten nicht geöffnet werden.",
        "opendeck": "OpenDeck",
        "opendeck_installed_success": "OpenDeck Plugin erfolgreich installiert.",
        "error_plugin_not_found": "Quell-Plugin nicht gefunden.",
        "error_whisper": "Whisper Fehler",
        "error_loading_model": "Fehler beim Laden des Modells",

        "settings_title": "Einstellungen - OpenDictate",
        "tab_general": "Allgemein",
        "tab_apps": "Anwendungen",
        "tab_ai": "KI & Modelle",
        "tab_models": "Modell-Manager",
        "tab_advanced": "Erweitert",
        
        "ui_language": "UI-Sprache:",
        "transcription_language": "Transkriptionssprache:",
        "transcription_auto": "Automatisch",
        
        "lbl_autosend": "Nach Abschluss automatisch senden",
        "lbl_realtime": "Echtzeit-Chunk-Analyse",
        "realtime_enabled": "Echtzeit: Aktiviert",
        "realtime_disabled": "Echtzeit: Deaktiviert",
        "lbl_ai_enabled": "KI-Bereinigung und Formatierung",
        "lbl_hide_bubble": "Textblase ausblenden",
        "lbl_auto_pause": "Medien automatisch pausieren",
        "lbl_autostart": "Mit System starten",
        "lbl_notifications": "Systembenachrichtigungen anzeigen",
        "lbl_vad": "VAD-Filter (Anti-Rauschen)",
        
        "btn_save_general": "Allgemeine Einstellungen speichern",
        "btn_save_ai": "KI-Einstellungen speichern",
        "btn_save_adv": "Erweiterte Einstellungen speichern",
        
        "lbl_provider": "API-Anbieter:",
        "lbl_api_key": "API-Schlüssel:",
        "lbl_model": "Modell (Gemini):",
        "lbl_sys_prompt": "System-Prompt:",
        "lbl_llm_timeout": "Zeitüberschreitung LLM (s):",
        "lbl_llm_temp": "Temperatur LLM:",
        "lbl_llm_thinking": "KI-Denkmodus aktivieren (Chain of Thought):",
        
        "lbl_whisper_model": "Whisper-Modell:",
        "lbl_vad": "VAD-Filter (Ignorieren):",
        "lbl_beam": "Präzision (Beam Size):",
        "lbl_temp": "Temperatur:",
        
        "lbl_app_select": "Wählen Sie eine Anwendung",
        "lbl_vision": "Vision aktivieren (Bildschirmanalyse)",
        "lbl_app_class": "Fensterklassenname (z. B. google-chrome):",
        "btn_add_rule": "Regel hinzufügen/aktualisieren",
        "btn_delete": "Löschen",
        
        "msg_saved_title": "Gespeichert",
        "msg_saved_general": "Allgemeine Einstellungen erfolgreich gespeichert.",
        "msg_saved_ai": "KI-Einstellungen erfolgreich gespeichert.",
        "msg_saved_adv": "Erweiterte Einstellungen erfolgreich gespeichert.",
        "msg_rule_added": "Regel für {} erfolgreich gespeichert.",
        "msg_rule_deleted": "Regel für {} gelöscht.",
        "msg_select_app": "Wählen Sie eine Anwendung",
        
        "model_downloaded": "✅ Heruntergeladen",
        "model_not_downloaded": "❌ Nicht heruntergeladen",
        "btn_activate": "Aktivieren",
        "active_model": " (Aktiv)"
    },
    "fr": {
        "ready": "Prêt ({})",
        "recording": "Enregistrement...",
        "paused": "En pause",
        "transcribing": "Transcription...",
        "cleaning": "Nettoyage du texte...",
        "processing": "Traitement...",
        "ai_enabled": "IA : Activée",
        "ai_disabled": "IA : Désactivée",
        "autosend_enabled": "Envoi automatique : Activé",
        "autosend_disabled": "Envoi automatique : Désactivé",
        "autopause_enabled": "Pause auto des médias : Activée",
        "autopause_disabled": "Pause auto des médias : Désactivée",
        "bubble_visible": "Bulle : Visible",
        "bubble_hidden": "Bulle : Masquée",
        "error": "Erreur : {}",
        "copied": "Copié dans le presse-papiers",
        "quit": "Quitter",
        "settings": "Paramètres",
        
        "close": "Fermer",
        "copy_clipboard": "Copier dans le presse-papiers",
        "insert_text": "Insérer",
        "loading_model": "Chargement du modèle...",
        "loading_model_param": "Chargement de {size}...",
        "whisper_model": "Modèle Whisper",
        "auto_send": "Envoi automatique (Entrée)",
        "ai_cleanup": "Nettoyage IA",
        "opendeck_installed": "✅ OpenDeck : Installé",
        "opendeck_not_installed": "❌ OpenDeck : Non installé",
        "error_opening_config": "Impossible d'ouvrir les paramètres.",
        "opendeck": "OpenDeck",
        "opendeck_installed_success": "Plugin OpenDeck installé avec succès.",
        "error_plugin_not_found": "Plugin source introuvable.",
        "error_whisper": "Erreur Whisper",
        "error_loading_model": "Erreur lors du chargement du modèle",

        "settings_title": "Paramètres - OpenDictate",
        "tab_general": "Général",
        "tab_apps": "Applications",
        "tab_ai": "IA et Modèles",
        "tab_models": "Gestionnaire de Modèles",
        "tab_advanced": "Avancé",
        
        "ui_language": "Langue de l'interface :",
        "transcription_language": "Langue de transcription :",
        "transcription_auto": "Automatique",
        
        "lbl_autosend": "Envoi automatique à la fin",
        "lbl_realtime": "Analyse en temps réel (Chunks)",
        "realtime_enabled": "Temps réel : Activé",
        "realtime_disabled": "Temps réel : Désactivé",
        "lbl_ai_enabled": "Nettoyage et formatage IA",
        "lbl_hide_bubble": "Masquer la bulle de texte",
        "lbl_auto_pause": "Pause auto des médias",
        "lbl_autostart": "Démarrer avec le système",
        "lbl_notifications": "Afficher les notifications système",
        "lbl_vad": "Filtre VAD (Anti-bruit)",
        
        "btn_save_general": "Enregistrer les paramètres généraux",
        "btn_save_ai": "Enregistrer les paramètres IA",
        "btn_save_adv": "Enregistrer les paramètres avancés",
        
        "lbl_provider": "Fournisseur d'API :",
        "lbl_api_key": "Clé API :",
        "lbl_model": "Modèle (Gemini) :",
        "lbl_sys_prompt": "Prompt Système :",
        "lbl_llm_timeout": "Délai d'attente LLM (s) :",
        "lbl_llm_temp": "Température LLM :",
        "lbl_llm_thinking": "Activer le mode de réflexion IA (Chain of Thought) :",
        
        "lbl_whisper_model": "Modèle Whisper :",
        "lbl_vad": "Filtre VAD (Ignorer silences) :",
        "lbl_beam": "Précision (Beam Size) :",
        "lbl_temp": "Température :",
        
        "lbl_app_select": "Sélectionnez une application",
        "lbl_vision": "Activer Vision (Analyse de l'écran)",
        "lbl_app_class": "Nom de classe de fenêtre (ex: google-chrome) :",
        "btn_add_rule": "Ajouter / Mettre à jour la règle",
        "btn_delete": "Supprimer",
        
        "msg_saved_title": "Enregistré",
        "msg_saved_general": "Paramètres généraux enregistrés avec succès.",
        "msg_saved_ai": "Paramètres IA enregistrés avec succès.",
        "msg_saved_adv": "Paramètres avancés enregistrés avec succès.",
        "msg_rule_added": "Règle pour {} enregistrée avec succès.",
        "msg_rule_deleted": "Règle pour {} supprimée.",
        "msg_select_app": "Sélectionnez une application",
        
        "model_downloaded": "✅ Téléchargé",
        "model_not_downloaded": "❌ Non téléchargé",
        "btn_activate": "Activer",
        "active_model": " (Actif)"
    }
}

class Translator:
    def __init__(self, lang_code):
        self.lang = lang_code
        if not self.lang or self.lang not in TRANSLATIONS:
            self.lang = DEFAULT_LANG
            self.lang = DEFAULT_LANG

    def t(self, key, *args, **kwargs):
        text = TRANSLATIONS[self.lang].get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                pass
        if args:
            try:
                if isinstance(args[0], dict):
                    return text.format(**args[0])
                return text.format(*args)
            except Exception:
                pass
        return text

def get_translator(lang_code):
    return Translator(lang_code)
