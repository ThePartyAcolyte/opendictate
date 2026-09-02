import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "I18n.js" as I18n

PanelWindow {
  id: root

  property bool open: false
  property var stateData: null
  property string currentTab: "general"
  property bool showApiKey: false
  property string toastMessage: ""

  // Local draft state for input fields to prevent polling resets
  property string draftApiKey: ""
  property string draftGlobalPrompt: ""
  property string selectedProfileApp: ""
  property string draftProfileAppClass: ""
  property string draftProfilePrompt: ""
  property bool draftProfileVision: false
  property bool isCreatingNewProfile: false
  property bool autostartActive: false

  readonly property var config: stateData && stateData.config ? stateData.config : ({})
  readonly property var appProfiles: stateData && stateData.app_profiles ? stateData.app_profiles : []
  readonly property var openWindows: stateData && stateData.open_windows ? stateData.open_windows : []
  readonly property var voiceActions: stateData && stateData.voice_actions ? stateData.voice_actions : []
  readonly property string currentLang: cfgValue("ui_language", "es")

  function t(key, fallback) {
    return I18n.get(currentLang, key, fallback)
  }

  function cfgValue(key, fallback) {
    if (config && config[key] !== undefined && config[key] !== null) return config[key]
    return fallback
  }

  function cfgBool(key, fallback) {
    var val = cfgValue(key, fallback)
    return val === true || val === "true" || val === 1
  }

  function cfgNum(key, fallback) {
    var val = cfgValue(key, fallback)
    var n = Number(val)
    return isNaN(n) ? fallback : n
  }

  function updateConfig(key, val) {
    Quickshell.execDetached(["opendictate", "--set-config", String(key), String(val)])
    if (root.stateData && root.stateData.config) {
      root.stateData.config[key] = val
    }
  }

  function toggleConfig(key) {
    var curr = cfgBool(key, false)
    updateConfig(key, !curr)
  }

  function copyText(text, label) {
    Quickshell.execDetached(["wl-copy", text])
    showToast("✔ " + label + " " + t("toast_copied"))
  }

  function showToast(msg) {
    root.toastMessage = msg
    toastTimer.restart()
  }

  function selectProfile(app) {
    root.selectedProfileApp = app
    root.isCreatingNewProfile = false
    var found = false
    for (var i = 0; i < root.appProfiles.length; i++) {
      if (root.appProfiles[i].app_class === app) {
        root.draftProfileAppClass = root.appProfiles[i].app_class
        root.draftProfilePrompt = root.appProfiles[i].system_prompt || ""
        root.draftProfileVision = root.appProfiles[i].enable_vision || false
        found = true
        break
      }
    }
    if (!found) {
      root.draftProfileAppClass = app
      root.draftProfilePrompt = ""
      root.draftProfileVision = false
    }
  }

  function saveSelectedProfile() {
    var app = root.draftProfileAppClass.trim()
    if (!app) return
    var payload = JSON.stringify({
      app_class: app,
      system_prompt: root.draftProfilePrompt,
      enable_vision: root.draftProfileVision
    })
    Quickshell.execDetached(["opendictate", "--save-profile", payload])
    root.selectedProfileApp = app
    root.isCreatingNewProfile = false
    showToast(t("toast_profile_saved"))
  }

  function deleteSelectedProfile() {
    var app = root.draftProfileAppClass.trim()
    if (!app) return
    Quickshell.execDetached(["opendictate", "--delete-profile", app])
    root.selectedProfileApp = ""
    root.draftProfileAppClass = ""
    root.draftProfilePrompt = ""
    root.draftProfileVision = false
    root.isCreatingNewProfile = false
    showToast(t("toast_profile_deleted"))
  }

  Timer {
    id: toastTimer
    interval: 2500
    onTriggered: root.toastMessage = ""
  }

  visible: open
  anchors { top: true; bottom: true; left: true; right: true }
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore

  WlrLayershell.namespace: "omarchy-opendictate-settings"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

  Process {
    id: autostartCheckProc
    command: ["sh", "-c", "test -f \"$HOME/.config/autostart/opendictate.desktop\" && echo 1 || echo 0"]
    stdout: StdioCollector {
      onDataChanged: {
        root.autostartActive = text.trim() === "1"
      }
    }
  }

  onOpenChanged: {
    if (open) {
      autostartCheckProc.running = true
      root.draftApiKey = root.cfgValue("api_key", "")
      root.draftGlobalPrompt = root.cfgValue("base_system_prompt", "Eres un asistente de transcripción y corrección. Corrige puntuación y formato sin alterar el significado.")
      if (root.appProfiles.length > 0 && !root.selectedProfileApp) {
        root.selectProfile(root.appProfiles[0].app_class)
      }
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
    }
  }

  // Backdrop Scrim (click to dismiss)
  Rectangle {
    anchors.fill: parent
    color: Color.menu.scrim || Qt.rgba(0, 0, 0, 0.65)

    MouseArea {
      anchors.fill: parent
      onClicked: root.open = false
    }
  }

  // Centered Modal Window Card
  Rectangle {
    id: modalCard
    anchors.centerIn: parent
    width: Math.min(Style.space(980), parent.width - Style.space(40))
    height: Math.min(Style.space(720), parent.height - Style.space(40))
    radius: Style.cornerRadius > 0 ? Style.cornerRadius : 12
    color: Color.background
    border.color: Color.popups.border
    border.width: 1

    // Absorb clicks inside the modal card so they never fall through to the background scrim
    MouseArea {
      anchors.fill: parent
      onClicked: {}
    }

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.open = false

      ColumnLayout {
        anchors.fill: parent
        anchors.margins: Style.space(16)
        spacing: Style.space(12)

        // ===================================================================
        // HEADER
        // ===================================================================
        RowLayout {
          Layout.fillWidth: true
          spacing: Style.space(12)

          Text {
            text: "󰍬"
            font.family: Style.font.family
            font.pixelSize: Style.font.display
            color: Color.accent
          }

          ColumnLayout {
            spacing: 2

            Text {
              text: root.t("settings_title")
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
              color: Color.foreground
            }

            Text {
              text: root.t("settings_subtitle")
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              color: Color.muted
            }
          }

          Item { Layout.fillWidth: true }

          // Toast Banner
          Rectangle {
            visible: root.toastMessage !== ""
            implicitWidth: toastLabel.implicitWidth + Style.space(16)
            implicitHeight: 28
            radius: 6
            color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.2)
            border.color: Color.accent
            border.width: 1

            Text {
              id: toastLabel
              anchors.centerIn: parent
              text: root.toastMessage
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
              color: Color.accent
            }
          }

          // Esc Hint
          Rectangle {
            implicitWidth: escText.implicitWidth + Style.space(14)
            implicitHeight: 26
            radius: 4
            color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.06)
            border.color: Color.popups.border
            border.width: 1

            Text {
              id: escText
              anchors.centerIn: parent
              text: root.t("press_esc_exit")
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              color: Color.muted
            }
          }
        }

        PanelSeparator { Layout.fillWidth: true }

        // ===================================================================
        // MAIN BODY: FIXED SIDEBAR + EXPANDABLE CONTENT AREA
        // ===================================================================
        RowLayout {
          Layout.fillWidth: true
          Layout.fillHeight: true
          spacing: Style.space(14)

          // Left Sidebar Tabs
          ColumnLayout {
            Layout.preferredWidth: Style.space(220)
            Layout.minimumWidth: Style.space(220)
            Layout.maximumWidth: Style.space(220)
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: Style.space(6)

            Button {
              Layout.fillWidth: true
              text: root.t("tab_general")
              selected: root.currentTab === "general"
              onClicked: root.currentTab = "general"
            }

            Button {
              Layout.fillWidth: true
              text: root.t("tab_ai")
              selected: root.currentTab === "ai"
              onClicked: root.currentTab = "ai"
            }

            Button {
              Layout.fillWidth: true
              text: root.t("tab_advanced")
              selected: root.currentTab === "advanced"
              onClicked: root.currentTab = "advanced"
            }

            Button {
              Layout.fillWidth: true
              text: root.t("tab_models")
              selected: root.currentTab === "models"
              onClicked: root.currentTab = "models"
            }

            Button {
              Layout.fillWidth: true
              text: root.t("tab_voice")
              selected: root.currentTab === "voice"
              onClicked: root.currentTab = "voice"
            }

            Button {
              Layout.fillWidth: true
              text: root.t("tab_shortcuts")
              selected: root.currentTab === "shortcuts"
              onClicked: root.currentTab = "shortcuts"
            }

            Item { Layout.fillHeight: true }

            PanelSeparator { Layout.fillWidth: true }

            Button {
              Layout.fillWidth: true
              text: root.t("btn_restart_daemon")
              onClicked: {
                Quickshell.execDetached(["opendictate", "--quit"])
                root.showToast(root.t("toast_daemon_restarted"))
              }
            }
          }

          // Vertical Separator
          Rectangle {
            Layout.fillHeight: true
            width: 1
            color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.12)
          }

          // Right Scrollable Content
          Flickable {
            id: flickArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: contentCol.implicitHeight + Style.space(30)
            clip: true
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
              id: contentCol
              width: parent.width - Style.space(16)
              spacing: Style.space(14)

              // =============================================================
              // TAB 1: GENERAL
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "general"
                Layout.fillWidth: true
                spacing: Style.space(10)

                PanelSectionHeader { text: root.t("sec_iface_system") }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_ui_language"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button { text: "Español"; selected: root.currentLang === "es"; onClicked: root.updateConfig("ui_language", "es") }
                  Button { text: "English"; selected: root.currentLang === "en"; onClicked: root.updateConfig("ui_language", "en") }
                  Button { text: "Deutsch"; selected: root.currentLang === "de"; onClicked: root.updateConfig("ui_language", "de") }
                  Button { text: "Français"; selected: root.currentLang === "fr"; onClicked: root.updateConfig("ui_language", "fr") }
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_desktop_integration"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button { text: root.t("opt_omarchy_bar"); selected: root.cfgValue("indicator_mode", "omarchy") === "omarchy"; onClicked: root.updateConfig("indicator_mode", "omarchy") }
                  Button { text: root.t("opt_none"); selected: root.cfgValue("indicator_mode", "omarchy") === "none"; onClicked: root.updateConfig("indicator_mode", "none") }
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_bar_position"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button {
                    text: root.t("opt_bar_left")
                    onClicked: Quickshell.execDetached(["opendictate", "--set-bar-position", "left"])
                  }
                  Button {
                    text: root.t("opt_bar_center")
                    onClicked: Quickshell.execDetached(["opendictate", "--set-bar-position", "center"])
                  }
                  Button {
                    text: root.t("opt_bar_right")
                    onClicked: Quickshell.execDetached(["opendictate", "--set-bar-position", "right"])
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_dictation_behavior") }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_stt_backend"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button { text: root.t("opt_whisper_local"); selected: root.cfgValue("stt_backend", "local_whisper") === "local_whisper"; onClicked: root.updateConfig("stt_backend", "local_whisper") }
                  Button { text: root.t("opt_gemini_live"); selected: root.cfgValue("stt_backend", "local_whisper") === "gemini_live"; onClicked: root.updateConfig("stt_backend", "gemini_live") }
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_autostart")
                  description: root.t("desc_autostart")
                  checked: root.autostartActive
                  onClicked: {
                    Quickshell.execDetached(["opendictate", "--toggle-autostart"])
                    root.autostartActive = !root.autostartActive
                  }
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_auto_send")
                  description: root.t("desc_auto_send")
                  checked: root.cfgBool("auto_send", false)
                  onClicked: root.toggleConfig("auto_send")
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_ai_enabled")
                  description: root.t("desc_ai_enabled")
                  checked: root.cfgBool("ai_enabled", false)
                  onClicked: root.toggleConfig("ai_enabled")
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_restore_focus")
                  description: root.t("desc_restore_focus")
                  checked: root.cfgBool("restore_window_focus", false)
                  onClicked: root.toggleConfig("restore_window_focus")
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_auto_pause")
                  description: root.t("desc_auto_pause")
                  checked: root.cfgBool("auto_pause_media", true)
                  onClicked: root.toggleConfig("auto_pause_media")
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_show_notifications")
                  description: root.t("desc_show_notifications")
                  checked: root.cfgBool("show_notifications", true)
                  onClicked: root.toggleConfig("show_notifications")
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_updates") }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_check_updates")
                  description: root.t("desc_check_updates")
                  checked: root.cfgBool("check_updates", false)
                  onClicked: root.toggleConfig("check_updates")
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_update_channel"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                  Button { text: root.t("opt_stable"); selected: root.cfgValue("update_channel", "stable") === "stable"; onClicked: root.updateConfig("update_channel", "stable") }
                  Button { text: root.t("opt_beta"); selected: root.cfgValue("update_channel", "stable") === "beta"; onClicked: root.updateConfig("update_channel", "beta") }
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_update_freq"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                  Button { text: root.t("opt_daily"); selected: root.cfgValue("update_frequency", "monthly") === "daily"; onClicked: root.updateConfig("update_frequency", "daily") }
                  Button { text: root.t("opt_weekly"); selected: root.cfgValue("update_frequency", "monthly") === "weekly"; onClicked: root.updateConfig("update_frequency", "weekly") }
                  Button { text: root.t("opt_monthly"); selected: root.cfgValue("update_frequency", "monthly") === "monthly"; onClicked: root.updateConfig("update_frequency", "monthly") }
                }
              }

              // =============================================================
              // TAB 2: PROCESAMIENTO CON IA & PERFILES POR APP
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "ai"
                Layout.fillWidth: true
                spacing: Style.space(12)

                // 1. API KEY CARD AT THE VERY TOP
                PanelSectionHeader { text: root.t("sec_api_credentials") }

                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: 64
                  radius: 8
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.05)
                  border.color: Color.popups.border
                  border.width: 1

                  RowLayout {
                    anchors.fill: parent
                    anchors.margins: Style.space(10)
                    spacing: Style.space(8)

                    Text {
                      text: root.t("lbl_api_key")
                      color: Color.foreground
                      font.family: Style.font.family
                      font.pixelSize: Style.font.body
                      font.bold: true
                    }

                    Rectangle {
                      Layout.fillWidth: true
                      height: 34
                      radius: 6
                      color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.08)
                      border.color: Color.popups.border
                      border.width: 1

                      TextInput {
                        id: apiKeyInput
                        anchors.fill: parent
                        anchors.margins: Style.space(6)
                        text: root.draftApiKey
                        echoMode: root.showApiKey ? TextInput.Normal : TextInput.Password
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        onTextChanged: root.draftApiKey = text
                        onEditingFinished: root.updateConfig("api_key", text)
                      }
                    }

                    Button {
                      text: root.showApiKey ? "󰈈" : "󰈉"
                      onClicked: root.showApiKey = !root.showApiKey
                    }

                    Button {
                      text: root.t("btn_save_key")
                      onClicked: {
                        root.updateConfig("api_key", root.draftApiKey)
                        root.showToast(root.t("toast_api_saved"))
                      }
                    }
                  }
                }

                PanelSeparator { Layout.fillWidth: true }

                // 2. GEMINI LIVE STT SECTION
                PanelSectionHeader { text: root.t("sec_gemini_live") }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_gemini_live_mode"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                  Button { text: root.t("opt_smart"); selected: root.cfgValue("gemini_live_mode", "SMART") === "SMART"; onClicked: root.updateConfig("gemini_live_mode", "SMART") }
                  Button { text: root.t("opt_verbatim"); selected: root.cfgValue("gemini_live_mode", "SMART") === "VERBATIM"; onClicked: root.updateConfig("gemini_live_mode", "VERBATIM") }
                }

                PanelSeparator { Layout.fillWidth: true }

                // 3. LLM POST-PROCESSING & CORRECTION
                PanelSectionHeader { text: root.t("sec_llm_postprocessing") }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_llm_model"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button { text: "Gemma 4 26B"; selected: root.cfgValue("model", "gemma-4-26b-a4b-it") === "gemma-4-26b-a4b-it"; onClicked: root.updateConfig("model", "gemma-4-26b-a4b-it") }
                  Button { text: "Gemini 3.1 Flash"; selected: root.cfgValue("model", "") === "gemini-3.1-flash-live-preview"; onClicked: root.updateConfig("model", "gemini-3.1-flash-live-preview") }
                  Button { text: "Gemini 2.5 Flash"; selected: root.cfgValue("model", "") === "gemini-2.5-flash"; onClicked: root.updateConfig("model", "gemini-2.5-flash") }
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_thinking")
                  description: root.t("desc_thinking")
                  checked: root.cfgBool("llm_thinking", false)
                  onClicked: root.toggleConfig("llm_thinking")
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_thinking_level"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                  Button { text: root.t("opt_minimal"); selected: root.cfgValue("llm_thinking_level", "minimal") === "minimal"; onClicked: root.updateConfig("llm_thinking_level", "minimal") }
                  Button { text: root.t("opt_medium"); selected: root.cfgValue("llm_thinking_level", "minimal") === "medium"; onClicked: root.updateConfig("llm_thinking_level", "medium") }
                  Button { text: root.t("opt_deep"); selected: root.cfgValue("llm_thinking_level", "minimal") === "deep"; onClicked: root.updateConfig("llm_thinking_level", "deep") }
                }

                // LLM Temperature Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_llm_temp") + ": " + Number(llmTempSlider.value).toFixed(2)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: llmTempSlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 1.0
                    stepSize: 0.05
                    value: root.cfgNum("llm_temperature", 0.7)
                    onMoved: root.updateConfig("llm_temperature", Number(value.toFixed(2)))
                  }
                }

                // LLM Timeout Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_llm_timeout") + ": " + Math.round(llmTimeoutSlider.value) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: llmTimeoutSlider
                    Layout.fillWidth: true
                    from: 10
                    to: 600
                    stepSize: 5
                    value: root.cfgNum("llm_timeout", 120)
                    onMoved: root.updateConfig("llm_timeout", Math.round(value))
                  }
                }

                PanelSeparator { Layout.fillWidth: true }

                // 4. GLOBAL SYSTEM PROMPT
                PanelSectionHeader { text: root.t("sec_system_prompt") }

                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: 90
                  radius: 6
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.06)
                  border.color: Color.popups.border
                  border.width: 1

                  Flickable {
                    anchors.fill: parent
                    anchors.margins: Style.space(8)
                    contentWidth: width
                    contentHeight: globalPromptEdit.implicitHeight
                    clip: true
                    ScrollBar.vertical: ScrollBar {}

                    TextEdit {
                      id: globalPromptEdit
                      width: parent.width
                      text: root.draftGlobalPrompt
                      wrapMode: TextEdit.Wrap
                      color: Color.foreground
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      onTextChanged: root.draftGlobalPrompt = text
                      onEditingFinished: root.updateConfig("base_system_prompt", text)
                    }
                  }
                }

                RowLayout {
                  Layout.fillWidth: true
                  Button {
                    text: root.t("btn_save_prompt")
                    onClicked: {
                      root.updateConfig("base_system_prompt", root.draftGlobalPrompt)
                      root.showToast(root.t("toast_prompt_saved"))
                    }
                  }
                }

                PanelSeparator { Layout.fillWidth: true }

                // 5. PER-APP AI PROFILES & OPEN WINDOW PICKER
                PanelSectionHeader { text: root.t("sec_app_profiles") }

                Text {
                  text: root.t("desc_app_profiles")
                  color: Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
                }

                // Configured App Selector Pills & Add Button
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(6)

                  Flickable {
                    Layout.fillWidth: true
                    implicitHeight: 36
                    contentWidth: appPillsRow.implicitWidth
                    clip: true

                    Row {
                      id: appPillsRow
                      spacing: Style.space(6)

                      Repeater {
                        model: root.appProfiles

                        Button {
                          text: modelData.app_class
                          selected: root.selectedProfileApp === modelData.app_class && !root.isCreatingNewProfile
                          onClicked: root.selectProfile(modelData.app_class)
                        }
                      }
                    }
                  }

                  Button {
                    text: root.t("btn_new_profile")
                    selected: root.isCreatingNewProfile
                    onClicked: {
                      root.isCreatingNewProfile = true
                      root.selectedProfileApp = ""
                      root.draftProfileAppClass = ""
                      root.draftProfilePrompt = ""
                      root.draftProfileVision = false
                    }
                  }
                }

                // Detected Open Windows Picker (shown when adding a new profile or no profiles exist)
                ColumnLayout {
                  visible: root.isCreatingNewProfile || root.appProfiles.length === 0
                  Layout.fillWidth: true
                  spacing: Style.space(6)

                  Text {
                    text: root.t("lbl_detected_windows")
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    font.bold: true
                  }

                  Text {
                    text: root.t("desc_detected_windows")
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                  }

                  // Open Windows Grid / Flow
                  Flow {
                    Layout.fillWidth: true
                    spacing: Style.space(6)

                    Repeater {
                      model: root.openWindows

                      Button {
                        text: (modelData.app_name || modelData.class) + " (" + modelData.class + ")"
                        selected: root.draftProfileAppClass === modelData.class
                        onClicked: {
                          root.draftProfileAppClass = modelData.class
                          root.selectProfile(modelData.class)
                          root.isCreatingNewProfile = true
                        }
                      }
                    }
                  }
                }

                // Profile Editor Card
                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: profileCol.implicitHeight + Style.space(20)
                  radius: 8
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.05)
                  border.color: Color.popups.border
                  border.width: 1

                  ColumnLayout {
                    id: profileCol
                    anchors.fill: parent
                    anchors.margins: Style.space(10)
                    spacing: Style.space(8)

                    RowLayout {
                      Layout.fillWidth: true
                      spacing: Style.space(8)

                      Text {
                        text: root.t("lbl_custom_app_class")
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                      }

                      Rectangle {
                        Layout.fillWidth: true
                        height: 32
                        radius: 4
                        color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.08)
                        border.color: Color.popups.border
                        border.width: 1

                        TextInput {
                          id: appClassInput
                          anchors.fill: parent
                          anchors.margins: Style.space(6)
                          text: root.draftProfileAppClass
                          color: Color.foreground
                          font.family: Style.font.family
                          font.pixelSize: Style.font.body
                          onTextChanged: root.draftProfileAppClass = text

                          Text {
                            anchors.fill: parent
                            visible: !appClassInput.text && !appClassInput.activeFocus
                            text: root.t("placeholder_new_app")
                            color: Color.muted
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                          }
                        }
                      }
                    }

                    Text {
                      text: root.t("lbl_profile_prompt")
                      color: Color.foreground
                      font.family: Style.font.family
                      font.pixelSize: Style.font.body
                    }

                    Rectangle {
                      Layout.fillWidth: true
                      implicitHeight: 90
                      radius: 6
                      color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.06)
                      border.color: Color.popups.border
                      border.width: 1

                      Flickable {
                        anchors.fill: parent
                        anchors.margins: Style.space(6)
                        contentWidth: width
                        contentHeight: appPromptEdit.implicitHeight
                        clip: true
                        ScrollBar.vertical: ScrollBar {}

                        TextEdit {
                          id: appPromptEdit
                          width: parent.width
                          text: root.draftProfilePrompt
                          wrapMode: TextEdit.Wrap
                          color: Color.foreground
                          font.family: Style.font.family
                          font.pixelSize: Style.font.caption
                          onTextChanged: root.draftProfilePrompt = text
                        }
                      }
                    }

                    Toggle {
                      Layout.fillWidth: true
                      label: root.t("lbl_profile_vision")
                      description: root.t("desc_profile_vision")
                      checked: root.draftProfileVision
                      onClicked: root.draftProfileVision = !root.draftProfileVision
                    }

                    RowLayout {
                      Layout.fillWidth: true
                      spacing: Style.space(8)

                      Button {
                        text: root.t("btn_save_profile")
                        onClicked: root.saveSelectedProfile()
                      }

                      Button {
                        text: root.t("btn_delete_profile")
                        visible: !root.isCreatingNewProfile && root.selectedProfileApp !== ""
                        foreground: Color.urgent
                        onClicked: root.deleteSelectedProfile()
                      }
                    }
                  }
                }
              }

              // =============================================================
              // TAB 3: WHISPER AVANZADO & SLIDERS
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "advanced"
                Layout.fillWidth: true
                spacing: Style.space(10)

                PanelSectionHeader { text: root.t("sec_streaming") }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_realtime_mode")
                  description: root.t("desc_realtime_mode")
                  checked: root.cfgBool("realtime_mode", true)
                  onClicked: root.toggleConfig("realtime_mode")
                }

                // Chunk Silence Duration Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_silence_threshold") + ": " + Number(chunkSilenceSlider.value).toFixed(2) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: chunkSilenceSlider
                    Layout.fillWidth: true
                    from: 0.10
                    to: 5.00
                    stepSize: 0.05
                    value: root.cfgNum("chunk_silence_duration", 0.85)
                    onMoved: root.updateConfig("chunk_silence_duration", Number(value.toFixed(2)))
                  }
                }

                // Chunk Max Duration Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_max_chunk") + ": " + Math.round(chunkMaxSlider.value) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: chunkMaxSlider
                    Layout.fillWidth: true
                    from: 5.0
                    to: 120.0
                    stepSize: 1.0
                    value: root.cfgNum("chunk_max_duration", 30.0)
                    onMoved: root.updateConfig("chunk_max_duration", Math.round(value))
                  }
                }

                // Chunk Fallback Silence Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_fallback_silence") + ": " + Number(chunkFallbackSlider.value).toFixed(2) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: chunkFallbackSlider
                    Layout.fillWidth: true
                    from: 0.10
                    to: 2.00
                    stepSize: 0.05
                    value: root.cfgNum("chunk_fallback_silence_duration", 0.50)
                    onMoved: root.updateConfig("chunk_fallback_silence_duration", Number(value.toFixed(2)))
                  }
                }

                // Chunk Min Duration Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_min_chunk") + ": " + Number(chunkMinSlider.value).toFixed(1) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: chunkMinSlider
                    Layout.fillWidth: true
                    from: 0.5
                    to: 10.0
                    stepSize: 0.5
                    value: root.cfgNum("chunk_min_duration", 3.0)
                    onMoved: root.updateConfig("chunk_min_duration", Number(value.toFixed(1)))
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_hardware") }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_device"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
                  Button { text: "Auto"; selected: root.cfgValue("whisper_device", "auto") === "auto"; onClicked: root.updateConfig("whisper_device", "auto") }
                  Button { text: "CUDA (NVIDIA)"; selected: root.cfgValue("whisper_device", "auto") === "cuda"; onClicked: root.updateConfig("whisper_device", "cuda") }
                  Button { text: "CPU"; selected: root.cfgValue("whisper_device", "auto") === "cpu"; onClicked: root.updateConfig("whisper_device", "cpu") }
                }

                RowLayout {
                  Layout.fillWidth: true
                  Text { Layout.fillWidth: true; text: root.t("lbl_compute_type"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                  Button { text: "Default"; selected: root.cfgValue("whisper_compute_type", "default") === "default"; onClicked: root.updateConfig("whisper_compute_type", "default") }
                  Button { text: "Float16"; selected: root.cfgValue("whisper_compute_type", "default") === "float16"; onClicked: root.updateConfig("whisper_compute_type", "float16") }
                  Button { text: "Int8"; selected: root.cfgValue("whisper_compute_type", "default") === "int8"; onClicked: root.updateConfig("whisper_compute_type", "int8") }
                  Button { text: "Int8_Float16"; selected: root.cfgValue("whisper_compute_type", "default") === "int8_float16"; onClicked: root.updateConfig("whisper_compute_type", "int8_float16") }
                }

                // CPU Threads Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_cpu_threads") + ": " + (Math.round(cpuThreadsSlider.value) === 0 ? "Auto" : Math.round(cpuThreadsSlider.value))
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: cpuThreadsSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 32
                    stepSize: 1
                    value: root.cfgNum("whisper_cpu_threads", 0)
                    onMoved: root.updateConfig("whisper_cpu_threads", Math.round(value))
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_whisper_engine") }

                // Whisper Temperature Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_whisper_temp") + ": " + Number(whisperTempSlider.value).toFixed(2)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: whisperTempSlider
                    Layout.fillWidth: true
                    from: 0.00
                    to: 1.00
                    stepSize: 0.05
                    value: root.cfgNum("temperature", 0.0)
                    onMoved: root.updateConfig("temperature", Number(value.toFixed(2)))
                  }
                }

                // Beam Size Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_beam_size") + ": " + Math.round(beamSizeSlider.value)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: beamSizeSlider
                    Layout.fillWidth: true
                    from: 1
                    to: 10
                    stepSize: 1
                    value: root.cfgNum("beam_size", 5)
                    onMoved: root.updateConfig("beam_size", Math.round(value))
                  }
                }

                // Repetition Penalty Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_rep_penalty") + ": " + Number(repPenaltySlider.value).toFixed(2)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: repPenaltySlider
                    Layout.fillWidth: true
                    from: 1.00
                    to: 2.00
                    stepSize: 0.05
                    value: root.cfgNum("repetition_penalty", 1.10)
                    onMoved: root.updateConfig("repetition_penalty", Number(value.toFixed(2)))
                  }
                }

                // No Repeat N-Gram Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_no_repeat_ngram") + ": " + Math.round(ngramSlider.value)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: ngramSlider
                    Layout.fillWidth: true
                    from: 0
                    to: 10
                    stepSize: 1
                    value: root.cfgNum("no_repeat_ngram_size", 0)
                    onMoved: root.updateConfig("no_repeat_ngram_size", Math.round(value))
                  }
                }

                // Hallucination Silence Threshold Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_hallucination_silence") + ": " + Number(hallucinationSlider.value).toFixed(1) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: hallucinationSlider
                    Layout.fillWidth: true
                    from: 0.5
                    to: 10.0
                    stepSize: 0.5
                    value: root.cfgNum("hallucination_silence_threshold", 2.0)
                    onMoved: root.updateConfig("hallucination_silence_threshold", Number(value.toFixed(1)))
                  }
                }

                // Beam Patience Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_beam_patience") + ": " + Number(beamPatienceSlider.value).toFixed(1)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: beamPatienceSlider
                    Layout.fillWidth: true
                    from: 0.5
                    to: 3.0
                    stepSize: 0.1
                    value: root.cfgNum("beam_patience", 1.0)
                    onMoved: root.updateConfig("beam_patience", Number(value.toFixed(1)))
                  }
                }

                // Length Penalty Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_length_penalty") + ": " + Number(lengthPenaltySlider.value).toFixed(1)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: lengthPenaltySlider
                    Layout.fillWidth: true
                    from: 0.0
                    to: 2.0
                    stepSize: 0.1
                    value: root.cfgNum("length_penalty", 1.0)
                    onMoved: root.updateConfig("length_penalty", Number(value.toFixed(1)))
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_vad_anti_loop") }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_vad_filter")
                  description: root.t("desc_vad_filter")
                  checked: root.cfgBool("vad_filter", false)
                  onClicked: root.toggleConfig("vad_filter")
                }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_condition_prev")
                  description: root.t("desc_condition_prev")
                  checked: root.cfgBool("condition_on_previous_text", true)
                  onClicked: root.toggleConfig("condition_on_previous_text")
                }

                // VAD Threshold Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_vad_threshold") + ": " + Number(vadThreshSlider.value).toFixed(2)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: vadThreshSlider
                    Layout.fillWidth: true
                    from: 0.10
                    to: 0.90
                    stepSize: 0.05
                    value: root.cfgNum("vad_threshold", 0.50)
                    onMoved: root.updateConfig("vad_threshold", Number(value.toFixed(2)))
                  }
                }

                // VAD Speech Pad Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_vad_speech_pad") + ": " + Math.round(speechPadSlider.value) + "ms"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: speechPadSlider
                    Layout.fillWidth: true
                    from: 50
                    to: 2000
                    stepSize: 50
                    value: root.cfgNum("vad_speech_pad_ms", 400)
                    onMoved: root.updateConfig("vad_speech_pad_ms", Math.round(value))
                  }
                }

                // VAD Min Silence Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_vad_min_silence") + ": " + Math.round(minSilenceSlider.value) + "ms"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: minSilenceSlider
                    Layout.fillWidth: true
                    from: 100
                    to: 5000
                    stepSize: 100
                    value: root.cfgNum("vad_min_silence_duration_ms", 2000)
                    onMoved: root.updateConfig("vad_min_silence_duration_ms", Math.round(value))
                  }
                }
              }

              // =============================================================
              // TAB 4: MODELOS WHISPER
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "models"
                Layout.fillWidth: true
                spacing: Style.space(10)

                PanelSectionHeader { text: root.t("sec_local_models") }

                Repeater {
                  model: [
                    { id: "tiny", name: "Whisper Tiny (39 MB)", desc: "Ultrarrápido, consumo mínimo de RAM (~500 MB). Ideal para hardware modesto." },
                    { id: "base", name: "Whisper Base (74 MB)", desc: "Muy rápido, buena precisión para dictado diario (~800 MB RAM)." },
                    { id: "small", name: "Whisper Small (244 MB)", desc: "Excelente balance velocidad/precisión. Muy recomendado (~1.5 GB RAM)." },
                    { id: "medium", name: "Whisper Medium (769 MB)", desc: "Alta precisión gramatical y técnica. Ideal para español (~3 GB RAM)." },
                    { id: "large-v3", name: "Whisper Large-v3 (1.5 GB)", desc: "Máxima precisión absoluta. Requiere GPU potente (~6 GB VRAM)." }
                  ]

                  Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 56
                    radius: 8
                    color: root.cfgValue("whisper_model_size", "medium") === modelData.id
                      ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.15)
                      : Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.05)
                    border.color: root.cfgValue("whisper_model_size", "medium") === modelData.id ? Color.accent : Color.popups.border
                    border.width: 1

                    RowLayout {
                      anchors.fill: parent
                      anchors.margins: Style.space(10)
                      spacing: Style.space(10)

                      ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        Text {
                          text: modelData.name + (root.cfgValue("whisper_model_size", "medium") === modelData.id ? "  ✔ " + root.t("btn_active").toUpperCase() : "")
                          font.family: Style.font.family
                          font.pixelSize: Style.font.body
                          font.bold: true
                          color: root.cfgValue("whisper_model_size", "medium") === modelData.id ? Color.accent : Color.foreground
                        }

                        Text {
                          text: modelData.desc
                          font.family: Style.font.family
                          font.pixelSize: Style.font.caption
                          color: Color.muted
                        }
                      }

                      Button {
                        text: root.cfgValue("whisper_model_size", "medium") === modelData.id ? root.t("btn_active") : root.t("btn_activate_model")
                        selected: root.cfgValue("whisper_model_size", "medium") === modelData.id
                        onClicked: {
                          root.updateConfig("whisper_model_size", modelData.id)
                          Quickshell.execDetached(["opendictate", "--cycle-model"])
                          root.showToast(root.t("toast_loading_model"))
                        }
                      }
                    }
                  }
                }
              }

              // =============================================================
              // TAB 5: COMANDOS DE VOZ & AEC
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "voice"
                Layout.fillWidth: true
                spacing: Style.space(10)

                PanelSectionHeader { text: root.t("sec_voice_triggers") }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_voice_commands")
                  description: root.t("desc_voice_commands")
                  checked: root.cfgBool("voice_commands_enabled", false)
                  onClicked: root.toggleConfig("voice_commands_enabled")
                }

                // Voice Command Match Threshold Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_voice_thresh") + ": " + Number(voiceThreshSlider.value).toFixed(2)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: voiceThreshSlider
                    Layout.fillWidth: true
                    from: 0.50
                    to: 0.90
                    stepSize: 0.01
                    value: root.cfgNum("voice_command_threshold", 0.70)
                    onMoved: root.updateConfig("voice_command_threshold", Number(value.toFixed(2)))
                  }
                }

                // Voice Command Silence Pause Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_voice_pause") + ": " + Number(voicePauseSlider.value).toFixed(1) + "s"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: voicePauseSlider
                    Layout.fillWidth: true
                    from: 0.2
                    to: 6.0
                    stepSize: 0.1
                    value: root.cfgNum("voice_command_silence_pause", 1.5)
                    onMoved: root.updateConfig("voice_command_silence_pause", Number(value.toFixed(1)))
                  }
                }

                // Voice VAD Threshold Slider
                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.preferredWidth: Style.space(250)
                    text: root.t("lbl_voice_vad_thresh") + ": " + Number(voiceVadSlider.value).toFixed(3)
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Slider {
                    id: voiceVadSlider
                    Layout.fillWidth: true
                    from: 0.010
                    to: 0.200
                    stepSize: 0.005
                    value: root.cfgNum("voice_vad_threshold", 0.075)
                    onMoved: root.updateConfig("voice_vad_threshold", Number(value.toFixed(3)))
                  }
                }

                // Noise Floor Calibration Card
                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: 46
                  radius: 6
                  color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.05)
                  border.color: Color.popups.border
                  border.width: 1

                  RowLayout {
                    anchors.fill: parent
                    anchors.margins: Style.space(8)
                    spacing: Style.space(10)

                    Text {
                      Layout.fillWidth: true
                      text: root.t("lbl_noise_floor_status") + " | Piso: " + Number(root.cfgNum("voice_vad_noise_floor", 0.030)).toFixed(3) + " / Umbral: " + Number(root.cfgNum("voice_vad_threshold", 0.075)).toFixed(3)
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      color: Color.muted
                    }

                    Button {
                      text: root.t("btn_calibrate_noise")
                      onClicked: {
                        Quickshell.execDetached(["opendictate", "--calibrate-noise"])
                        root.showToast("Calibrando ruido de fondo...")
                      }
                    }
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_voice_actions") }

                Repeater {
                  model: root.voiceActions

                  Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 48
                    radius: 6
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.04)

                    RowLayout {
                      anchors.fill: parent
                      anchors.margins: Style.space(8)
                      spacing: Style.space(10)

                      Text {
                        text: (modelData.icon || "🗣️") + " " + (modelData.label || modelData.action)
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                        color: Color.foreground
                      }

                      Text {
                        Layout.fillWidth: true
                        text: (modelData.phrases && modelData.phrases.length > 0) ? ("Frases: \"" + modelData.phrases.join("\", \"") + "\"") : "Sin frases"
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                        color: Color.muted
                        elide: Text.ElideRight
                      }
                    }
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_aec") }

                Toggle {
                  Layout.fillWidth: true
                  label: root.t("lbl_echo_cancel")
                  description: root.t("desc_echo_cancel")
                  checked: root.cfgBool("echo_cancellation_enabled", true)
                  onClicked: root.toggleConfig("echo_cancellation_enabled")
                }

                RowLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(8)

                  Text {
                    Layout.fillWidth: true
                    text: root.t("lbl_audio_device") + " " + (root.stateData && root.stateData.preferred_audio_device ? root.stateData.preferred_audio_device : "Default PulseAudio/PipeWire")
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                  }

                  Button {
                    text: root.t("btn_calibrate_aec")
                    onClicked: {
                      Quickshell.execDetached(["opendictate", "--calibrate-aec"])
                      root.showToast("Calibrando filtro AEC...")
                    }
                  }
                }
              }

              // =============================================================
              // TAB 6: ATAJOS Y CLI
              // =============================================================
              ColumnLayout {
                visible: root.currentTab === "shortcuts"
                Layout.fillWidth: true
                spacing: Style.space(10)

                PanelSectionHeader { text: root.t("sec_cli_commands") }

                Repeater {
                  model: [
                    { cmd: "opendictate --toggle-record-send", desc: "Alternar Grabación / Envío (Atajo principal)" },
                    { cmd: "opendictate --record", desc: "Iniciar grabación o reanudar pausa" },
                    { cmd: "opendictate --pause", desc: "Pausar la grabación actual" },
                    { cmd: "opendictate --send", desc: "Finalizar y enviar transcripción inmediatamente" },
                    { cmd: "opendictate --cancel", desc: "Cancelar y descartar la grabación en curso" },
                    { cmd: "opendictate --toggle-ai", desc: "Conmutar procesamiento con IA (On / Off)" },
                    { cmd: "opendictate --toggle-autosend", desc: "Conmutar envío automático con Enter" },
                    { cmd: "opendictate --settings", desc: "Abrir este panel de Ajustes en pantalla" }
                  ]

                  Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 46
                    radius: 6
                    color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.05)

                    RowLayout {
                      anchors.fill: parent
                      anchors.margins: Style.space(8)
                      spacing: Style.space(10)

                      Text {
                        text: modelData.cmd
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                        font.bold: true
                        color: Color.accent
                      }

                      Text {
                        Layout.fillWidth: true
                        text: modelData.desc
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption
                        color: Color.muted
                        elide: Text.ElideRight
                      }

                      Button {
                        text: root.t("btn_copy")
                        onClicked: root.copyText(modelData.cmd, modelData.cmd)
                      }
                    }
                  }
                }

                PanelSeparator { Layout.fillWidth: true }
                PanelSectionHeader { text: root.t("sec_hyprland_shortcut") }

                Rectangle {
                  Layout.fillWidth: true
                  implicitHeight: 46
                  radius: 6
                  color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.1)
                  border.color: Color.accent
                  border.width: 1

                  RowLayout {
                    anchors.fill: parent
                    anchors.margins: Style.space(8)
                    spacing: Style.space(10)

                    Text {
                      Layout.fillWidth: true
                      text: "bind = SUPER, D, exec, opendictate --toggle-record-send"
                      font.family: Style.font.family
                      font.pixelSize: Style.font.body
                      font.bold: true
                      color: Color.foreground
                    }

                    Button {
                      text: root.t("btn_copy_config")
                      onClicked: root.copyText("bind = SUPER, D, exec, opendictate --toggle-record-send", "Regla Hyprland")
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
